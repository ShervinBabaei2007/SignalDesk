"""SignalDesk — AI-powered news intelligence dashboard.

FastAPI application: REST API + static dashboard frontend.

Run locally:
    uvicorn app.main:app --reload   (from the backend/ directory)
"""

import asyncio
import csv
import hmac
import io
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import (config, demo, events, netguard, notifications, observability, pipeline, reliability, reporting,
               story_index, watches, workspace)
from . import stories as story_logic
from .database import SessionLocal, ensure_columns, engine, get_db
from .enrichment import enrich_article
from .ingestion import add_missing_default_feeds
from .models import NO_WORKSPACE, Article, Base, Feed
from .quality import backfill_info_scores
from .schemas import (ArticleDetail, ArticlePage, Digest, FeedCreate, FeedIngestResult, FeedOut,
                      IngestResult, SourceList, Stats, StoryDetail, StoryPage, StoryTimeline, TrendingStory, WatchAlertOut,
                      WatchIn, WatchOut, WatchPatch)
from .seed_data import backfill_keywords, repair_seed_dates, seed_if_empty

logger = logging.getLogger("signaldesk")

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
FRONTEND_DIR = BASE_DIR.parent / "frontend"

INGEST_INTERVAL_MINUTES = config.INGEST_INTERVAL_MINUTES
_started_at = time.time()


async def _scheduled_ingestion():
    """Auto-pilot: periodically run the ingestion pipeline in the background."""
    wait = 30  # first run shortly after boot, then on the regular interval
    while True:
        await asyncio.sleep(wait)
        wait = INGEST_INTERVAL_MINUTES * 60
        try:
            await asyncio.to_thread(pipeline.scheduled_cycle)
        except Exception:  # noqa: BLE001
            logger.exception("[scheduler] auto-ingest failed")


async def _scheduled_digest():
    """Deliver the daily brief once per day at DIGEST_HOUR (UTC)."""
    last_sent_date = None
    while True:
        await asyncio.sleep(60)
        if config.DIGEST_HOUR < 0 or not notifications.configured_channels():
            continue
        now = datetime.now(timezone.utc)
        if now.hour != config.DIGEST_HOUR or last_sent_date == now.date():
            continue
        last_sent_date = now.date()
        try:
            with SessionLocal() as db:
                digest = reporting.digest(db)
            result = notifications.deliver_digest(digest)
            logger.info("[digest] scheduled delivery: sent=%s errors=%s",
                        result["sent"], result["errors"])
        except Exception:  # noqa: BLE001
            logger.exception("[digest] scheduled delivery failed")


def init_database() -> None:
    """Create and migrate the schema, seed an empty database, and backfill derived columns (safe to repeat)."""
    Base.metadata.create_all(bind=engine)
    ensure_columns()
    with SessionLocal() as db:
        seeded = seed_if_empty(db, live=not config.SCHEDULER_DISABLED)
        if seeded:
            logger.info("[seed] First boot: populated %s articles", seeded)
        repaired = repair_seed_dates(db)
        if repaired:
            logger.info("[migrate] Moved %s future-dated sample articles back into the past", repaired)
        backfilled = backfill_keywords(db)
        if backfilled:
            logger.info("[migrate] Backfilled keywords for %s articles", backfilled)
        scores = backfill_info_scores(db)
        if scores["scored"]:
            logger.info("[migrate] Scored %s articles for information quality", scores["scored"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: prepare the database and run the background schedulers."""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("[boot] SignalDesk v%s (%s)", config.VERSION, config.APP_ENV)
    init_database()
    scheduler_task = None
    if INGEST_INTERVAL_MINUTES > 0 and not config.SCHEDULER_DISABLED:
        scheduler_task = asyncio.create_task(_scheduled_ingestion())
        logger.info("[scheduler] auto-ingest every %s minutes", INGEST_INTERVAL_MINUTES)
    digest_task = None
    if config.DIGEST_HOUR >= 0 and notifications.configured_channels():
        digest_task = asyncio.create_task(_scheduled_digest())
        logger.info("[digest] daily brief scheduled for %02d:00 UTC", config.DIGEST_HOUR)
    yield
    if scheduler_task:
        scheduler_task.cancel()
    if digest_task:
        digest_task.cancel()


app = FastAPI(
    title="SignalDesk API",
    description="Automated news research platform: RSS ingestion, AI analysis, intelligence dashboard.",
    version=config.VERSION,
    lifespan=lifespan,
)

_allow_all = config.CORS_ORIGINS == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_origin_regex=".*" if _allow_all else None,
    allow_credentials=not _allow_all,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add standard security headers to every response."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Last-resort handler: log the traceback, never leak internals to clients."""
    logger.exception("[error] unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _supplied_token(request: Request) -> str:
    """The token a request sent in X-API-Key or as a Bearer token, or an empty string."""
    supplied = request.headers.get("x-api-key", "")
    if not supplied:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            supplied = auth[7:].strip()
    return supplied


def request_workspace(request: Request) -> str:
    """The workspace a request belongs to: its signed token's id, else the shared base data."""
    return workspace.verify(_supplied_token(request)) or NO_WORKSPACE


def scoped_db(request: Request):
    """A database session that only sees the shared base data plus the caller's own workspace."""
    db = SessionLocal()
    token = _supplied_token(request)
    db.info["workspace"] = workspace.verify(token) or NO_WORKSPACE
    owner = bool(config.API_TOKEN and token and hmac.compare_digest(token, config.API_TOKEN))
    # Built-in sample articles (placeholder content, no page, no image) belong to the demo tour and plain
    # browsing only. A visitor's workspace and the owner's real session show real articles.
    db.info["hide_seeds"] = bool(db.info["workspace"]) or owner
    try:
        yield db
    finally:
        db.close()


def require_ingest_access(request: Request) -> None:
    """Let a workspace, a valid demo token (when demo mode is on) or the real API token run an ingest."""
    token = _supplied_token(request)
    if workspace.verify(token):
        return
    if config.API_TOKEN and config.DEMO_MODE and demo.is_valid(token, config.API_TOKEN):
        return
    require_api_token(request)


def require_writer(request: Request) -> None:
    """Let a visitor's own workspace, or the owner's API token, change data (the owner's token is open when unset)."""
    if workspace.verify(_supplied_token(request)):
        return
    require_api_token(request)


def require_api_token(request: Request) -> None:
    """Protect state-changing endpoints when API_TOKEN is configured.

    Accepts either `X-API-Key: <token>` or `Authorization: Bearer <token>`.
    Read-only endpoints stay public so the dashboard can render before login.
    """
    if not config.API_TOKEN:
        return
    supplied = _supplied_token(request)
    if not supplied or not hmac.compare_digest(supplied, config.API_TOKEN):
        raise HTTPException(
            401, "A valid API token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )


# --------------------------------------------------------------------------- #
# Static frontend
# --------------------------------------------------------------------------- #

DIST_DIR = FRONTEND_DIR / "dist"   # production build of the React app (npm run build)
_NO_CACHE = {"Cache-Control": "no-cache"}

if (DIST_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        """Serve the built dashboard's index.html."""
        return FileResponse(DIST_DIR / "index.html", headers=_NO_CACHE)
else:
    @app.get("/", include_in_schema=False)
    def index_missing():
        """Explain how to build the dashboard when no frontend build exists."""
        return HTMLResponse(
            "<h1>SignalDesk API is running</h1>"
            "<p>The dashboard hasn't been built yet. Run <code>cd frontend &amp;&amp; npm install "
            "&amp;&amp; npm run build</code>, or <code>npm run dev</code> for development. "
            "API docs: <a href='/docs'>/docs</a></p>"
        )


# --------------------------------------------------------------------------- #
# Health & stats
# --------------------------------------------------------------------------- #

@app.get("/api/health", tags=["System"])
def health(db: Session = Depends(scoped_db)):
    """Liveness probe reporting status, version, environment and uptime."""
    return {
        "status": "healthy",
        "version": config.VERSION,
        "env": config.APP_ENV,
        "uptime_seconds": round(time.time() - _started_at, 1),
        "features": {
            "llm_analysis": config.LLM_ENABLED,
            "digest_delivery": notifications.configured_channels(),
            "auth_required": bool(config.API_TOKEN),
        },
        "articles": db.scalar(select(func.count()).select_from(Article)),
        "feeds": db.scalar(select(func.count()).select_from(Feed)),
    }


@app.get("/api/auth/status", tags=["System"])
def auth_status():
    """Tell the dashboard whether mutating requests need an API token."""
    return {"required": bool(config.API_TOKEN), "demo": config.DEMO_MODE, "workspaces": workspace.enabled(),
            "workspace_ttl_days": config.WORKSPACE_TTL_DAYS}


def _client_ip(request: Request) -> str:
    """Best-effort client address (the first hop of X-Forwarded-For behind a proxy such as Vercel)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


@app.post("/api/workspace", status_code=201, tags=["Workspace"])
def create_workspace(request: Request):
    """Start a private workspace: the visitor's own feeds and watchlist, invisible to everyone else."""
    if not workspace.enabled():
        raise HTTPException(404, "Workspaces are not enabled")
    if not workspace.creations.allow(_client_ip(request)):
        raise HTTPException(429, "Too many workspaces created from this network; try again later")
    _, token = workspace.issue()
    return {"token": token, "expires_in_days": config.WORKSPACE_TTL_DAYS,
            "limits": {"feeds": config.WORKSPACE_MAX_FEEDS, "watches": config.WORKSPACE_MAX_WATCHES,
                       "articles": config.WORKSPACE_MAX_ARTICLES}}


@app.delete("/api/workspace", status_code=204, tags=["Workspace"])
def reset_workspace(request: Request, db: Session = Depends(scoped_db)):
    """Delete everything in the caller's workspace (the shared data is never touched)."""
    ws = request_workspace(request)
    if not ws:
        raise HTTPException(401, "A workspace token is required")
    workspace.reset(db, ws)


@app.post("/api/demo/session", tags=["System"])
def demo_session():
    """Start a demo: hand out a short-lived token that can run ingests but nothing else."""
    if not config.DEMO_MODE:
        raise HTTPException(404, "Demo mode is not enabled")
    token = demo.issue(config.API_TOKEN, config.DEMO_TTL_SECONDS) if config.API_TOKEN else ""
    return {"token": token, "expires_in": config.DEMO_TTL_SECONDS, "can": ["ingest"]}


@app.get("/api/observability", tags=["System"])
def pipeline_observability(hours: int = Query(24, ge=1, le=720), db: Session = Depends(scoped_db)):
    """Pipeline health for the shared data: run success and latency, throughput, failing feeds, extraction rate."""
    db.info["workspace"] = NO_WORKSPACE  # always the shared pipeline, whoever is asking
    return observability.summary(db, hours)


@app.get("/api/sources", response_model=SourceList, tags=["Intelligence"])
def source_profiles(db: Session = Depends(scoped_db)):
    """Evidence-based profile of each outlet: transparency, corrections, information, corroboration, availability."""
    return reliability.listing(db)


@app.get("/api/stats", response_model=Stats, tags=["System"])
def stats(db: Session = Depends(scoped_db)):
    """Dashboard totals, sentiment counts, topic breakdown and 7-day trend."""
    return reporting.stats(db)


# --------------------------------------------------------------------------- #
# Articles
# --------------------------------------------------------------------------- #

@app.get("/api/trending", response_model=list[TrendingStory], tags=["Intelligence"])
def trending_stories(limit: int = Query(story_index.HOT_STORIES, ge=1, le=20), db: Session = Depends(scoped_db)):
    """Hot topics: the stories the most outlets are covering right now."""
    return events.annotate_trending(db, story_index.trending(db, limit))


def _filtered(db: Session, search, source, topic, sentiment, cluster, hot, ids, order):
    """Validate the shared feed parameters and return (filtered select, order)."""
    sentiment = story_logic.clean(sentiment)
    order = story_logic.validate(sentiment, order)
    q = story_logic.apply_filters(
        db, select(Article),
        search=story_logic.clean(search), source=story_logic.clean(source), topic=story_logic.clean(topic),
        sentiment=sentiment, cluster=cluster, hot=hot, ids=story_logic.parse_ids(ids),
    )
    return q, order


@app.get("/api/articles", response_model=ArticlePage, tags=["Articles"])
def list_articles(
    search: str | None = Query(None, max_length=200),
    source: str | None = Query(None, max_length=200),
    topic: str | None = Query(None, max_length=50),
    sentiment: str | None = Query(None),
    cluster: int | None = Query(None, ge=1),
    hot: bool = Query(False),
    ids: str | None = Query(None, max_length=1500),
    order: str = Query("newest"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(scoped_db),
):
    """Flat list: every report on its own row."""
    q, order = _filtered(db, search, source, topic, sentiment, cluster, hot, ids, order)
    total = story_logic.count_matching(db, q)
    q = q.order_by(*story_logic.ordering(order))
    items = db.execute(q.offset(offset).limit(limit)).scalars().all()
    story_index.annotate(db, items)
    return ArticlePage(total=total, items=items, offset=offset, limit=limit)


@app.get("/api/stories", response_model=StoryPage, tags=["Articles"])
def list_stories(
    search: str | None = Query(None, max_length=200),
    source: str | None = Query(None, max_length=200),
    topic: str | None = Query(None, max_length=50),
    sentiment: str | None = Query(None),
    cluster: int | None = Query(None, ge=1),
    hot: bool = Query(False),
    ids: str | None = Query(None, max_length=1500),
    order: str = Query("newest"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(scoped_db),
):
    """Grouped list: one card per event, the best-informed report leading it."""
    q, order = _filtered(db, search, source, topic, sentiment, cluster, hot, ids, order)
    ordered = db.execute(q.with_only_columns(Article.id).order_by(*story_logic.ordering(order))).scalars().all()
    page = story_logic.build_page(db, list(ordered), offset, limit)
    return StoryPage(total=page["total"], article_total=page["article_total"],
                     items=page["stories"], offset=offset, limit=limit)


def _cluster_or_404(db: Session, cluster_id: int):
    """Return the cluster with this id, or raise 404 when the story no longer exists."""
    _, by_id = story_index.get_clusters(db)
    cluster = by_id.get(cluster_id)
    if cluster is None:
        raise HTTPException(404, "Story not found. It may have aged out or merged into another story.")
    return cluster


@app.get("/api/stories/{cluster_id}", response_model=StoryDetail, tags=["Articles"])
def story_detail(cluster_id: int, db: Session = Depends(scoped_db)):
    """One story in depth: its brief, how the outlets compare, and every report ranked."""
    return story_logic.story_detail(db, _cluster_or_404(db, cluster_id))


@app.get("/api/stories/{cluster_id}/timeline", response_model=StoryTimeline, tags=["Articles"])
def story_timeline(cluster_id: int, db: Session = Depends(scoped_db)):
    """How coverage of this story's event developed day by day (reports, outlets that joined, tone)."""
    return events.timeline(db, _cluster_or_404(db, cluster_id))


@app.post("/api/stories/{cluster_id}/brief", response_model=StoryDetail, tags=["Articles"],
          dependencies=[Depends(require_api_token)])
def refresh_story_brief(cluster_id: int, db: Session = Depends(scoped_db)):
    """Rewrite the story brief now (uses the language model when one is configured)."""
    return story_logic.story_detail(db, _cluster_or_404(db, cluster_id), force_brief=True)


# --------------------------------------------------------------------------- #
# Watchlist
# --------------------------------------------------------------------------- #

@app.exception_handler(watches.WatchError)
async def watch_error_handler(request: Request, exc: watches.WatchError):
    """Turn a watchlist rule violation into a JSON error with its HTTP status."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/api/watches", response_model=list[WatchOut], tags=["Watchlist"])
def list_watches(db: Session = Depends(scoped_db)):
    """List all watches with how many recent stories each currently matches."""
    return watches.with_counts(db, watches.all_watches(db))


@app.post("/api/watches", response_model=WatchOut, status_code=201, tags=["Watchlist"],
          dependencies=[Depends(require_writer)])
def create_watch(body: WatchIn, db: Session = Depends(scoped_db)):
    """Create a watch (token-protected when an API token is configured)."""
    watch = watches.create(db, body.term, body.topic, body.min_outlets)
    return watches.with_counts(db, [watch])[0]


@app.patch("/api/watches/{watch_id}", response_model=WatchOut, tags=["Watchlist"],
           dependencies=[Depends(require_writer)])
def update_watch(watch_id: int, body: WatchPatch, db: Session = Depends(scoped_db)):
    """Pause or resume a watch."""
    watch = watches.set_active(db, watch_id, body.is_active)
    return watches.with_counts(db, [watch])[0]


@app.delete("/api/watches/{watch_id}", status_code=204, tags=["Watchlist"],
            dependencies=[Depends(require_writer)])
def delete_watch(watch_id: int, db: Session = Depends(scoped_db)):
    """Delete a watch and its alert history."""
    watches.remove(db, watch_id)


@app.get("/api/articles/export.csv", tags=["Articles"])
def export_articles_csv(db: Session = Depends(scoped_db)):
    """Export every article as CSV, newest first."""
    items = db.execute(select(Article).order_by(Article.published_at.desc().nullslast())).scalars().all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "title", "source", "topic", "sentiment", "sentiment_label",
                     "url", "published_at", "keywords"])
    for a in items:
        writer.writerow([a.id, a.title, a.source, a.topic, a.sentiment, a.sentiment_label,
                         a.url, a.published_at.isoformat() if a.published_at else "", a.keywords or ""])
    buffer.seek(0)
    filename = f"signaldesk_articles_{datetime.now(timezone.utc):%Y%m%d}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/articles/{article_id}", response_model=ArticleDetail, tags=["Articles"])
def get_article(article_id: int, db: Session = Depends(scoped_db)):
    """Full detail for one article, including related reports of the same story."""
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(404, "Article not found")
    return _with_related(db, article)


def _with_related(db: Session, article: Article) -> Article:
    """Annotate an article with its story cluster and the other coverage of it."""
    story_index.annotate(db, [article])
    others = []
    if article.cluster_id:
        _, by_id = story_index.get_clusters(db)
        ids = [i for i in by_id[article.cluster_id].article_ids if i != article.id]
        # best-informed report first, so "Also covered by" is ranked, not just chronological
        others = story_logic.ranked(db.execute(select(Article).where(Article.id.in_(ids))).scalars().all())
    article.related = others
    return article


@app.post("/api/articles/{article_id}/summarize", response_model=ArticleDetail,
          tags=["Articles"], dependencies=[Depends(require_writer)])
def summarize_article(article_id: int, db: Session = Depends(scoped_db)):
    """Generate a clean, straightforward summary for one article on demand.

    Fetches the linked page (unless already enriched or a demo seed), extracts
    the readable text, and writes a deep summary. Falls back to stored feed
    text when the page can't be fetched — a summary is always returned.
    """
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(404, "Article not found")
    if article.enriched_at is None:
        enrich_article(db, article)
        db.refresh(article)
    return _with_related(db, article)


# --------------------------------------------------------------------------- #
# Digest
# --------------------------------------------------------------------------- #

@app.get("/api/digest", response_model=Digest, tags=["Intelligence"])
def daily_digest(db: Session = Depends(scoped_db)):
    """A generated intelligence brief: recent signals, extremes, and a headline."""
    return reporting.digest(db)


@app.post("/api/digest/send", tags=["Intelligence"],
          dependencies=[Depends(require_api_token)])
def send_digest(db: Session = Depends(scoped_db)):
    """Deliver the daily brief to every configured channel (Slack/email)."""
    if not notifications.configured_channels():
        raise HTTPException(
            400,
            "No digest channel configured — set SLACK_WEBHOOK_URL or "
            "DIGEST_EMAILS + SMTP_HOST.",
        )
    result = notifications.deliver_digest(reporting.digest(db))
    if not result["sent"]:
        raise HTTPException(502, f"Digest delivery failed: {result['errors']}")
    return result


# --------------------------------------------------------------------------- #
# Feeds & ingestion
# --------------------------------------------------------------------------- #

@app.get("/api/feeds", response_model=list[FeedOut], tags=["Feeds"])
def list_feeds(db: Session = Depends(scoped_db)):
    """List the configured RSS feeds."""
    return db.execute(select(Feed).order_by(Feed.name)).scalars().all()


@app.post("/api/feeds", response_model=FeedOut, status_code=201, tags=["Feeds"],
          dependencies=[Depends(require_writer)])
def create_feed(body: FeedCreate, db: Session = Depends(scoped_db)):
    """Add a new RSS feed."""
    parsed = urlparse(str(body.url))
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(422, "Feed URL must be an http(s) URL")
    owner_ws = db.info.get("workspace", NO_WORKSPACE)
    if owner_ws:  # a visitor's feed: public addresses only, and a cap so a workspace stays small
        try:
            netguard.check_url(str(body.url))
        except netguard.UnsafeURL as exc:
            raise HTTPException(422, str(exc)) from None
        if workspace.count(db, Feed, owner_ws) >= config.WORKSPACE_MAX_FEEDS:
            raise HTTPException(409, f"A workspace can have up to {config.WORKSPACE_MAX_FEEDS} feeds; remove one first")
    feed = Feed(name=body.name.strip(), url=str(body.url), workspace_id=owner_ws)
    db.add(feed)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "A feed with this name or URL already exists")
    db.refresh(feed)
    return feed


@app.post("/api/feeds/defaults", response_model=list[FeedOut], tags=["Feeds"],
          dependencies=[Depends(require_api_token)])
def add_default_feeds(db: Session = Depends(scoped_db)):
    """Add the recommended feeds that are missing. Returns only the newly added ones."""
    return add_missing_default_feeds(db)


@app.delete("/api/feeds/{feed_id}", status_code=204, tags=["Feeds"],
            dependencies=[Depends(require_writer)])
def delete_feed(feed_id: int, db: Session = Depends(scoped_db)):
    """Remove an RSS feed."""
    feed = db.get(Feed, feed_id)
    if not feed or feed.workspace_id != db.info.get("workspace", NO_WORKSPACE):
        raise HTTPException(404, "Feed not found")
    db.delete(feed)
    db.commit()


@app.get("/api/cron/ingest", include_in_schema=False)
def cron_ingest(request: Request):
    """Run one auto-pilot round when Vercel Cron calls (it sends CRON_SECRET as a Bearer token)."""
    supplied = request.headers.get("authorization", "")
    expected = f"Bearer {config.CRON_SECRET}"
    if not config.CRON_SECRET or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "Invalid cron secret")
    cycle = pipeline.scheduled_cycle()
    with SessionLocal() as db:
        purged = workspace.purge_expired(db)
    if purged:
        logger.info("[workspace] purged %s expired rows", purged)
    with SessionLocal() as db:
        observability.purge_old(db)
    return {"ran": cycle is not None, "added": sum(r["added"] for r in cycle.results) if cycle else 0}


@app.post("/api/ingest", response_model=IngestResult, tags=["Ingestion"],
          dependencies=[Depends(require_ingest_access)])
def ingest(db: Session = Depends(scoped_db), background_tasks: BackgroundTasks = None):
    """Fetch every active RSS feed, dedupe by URL, analyze, and store new articles.

    Full-text enrichment (fetching the linked pages and writing clean
    summaries) runs in the background right after the response.
    """
    try:
        cycle = pipeline.ingest_cycle(db, manual=True)
    except pipeline.Busy as busy:
        raise HTTPException(429, str(busy)) from None
    if background_tasks and cycle.enrich_needed:
        background_tasks.add_task(pipeline.enrich_backlog, workspace=db.info.get("workspace", NO_WORKSPACE))
    results = cycle.results
    return IngestResult(
        alerts=[WatchAlertOut(**a) for a in cycle.alerts],
        added=sum(r["added"] for r in results),
        fetched=sum(r["fetched"] for r in results),
        skipped=sum(r["skipped"] for r in results),
        results=[FeedIngestResult(**r) for r in results],
        duration_seconds=cycle.duration_seconds,
        enrich_queued=cycle.enrich_pending,
    )
