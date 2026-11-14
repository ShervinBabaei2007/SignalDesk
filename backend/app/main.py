"""SignalDesk — AI-powered news intelligence dashboard.

FastAPI application: REST API + static dashboard frontend.

Run locally:
    uvicorn app.main:app --reload   (from the backend/ directory)
"""

import asyncio
import hmac
import logging
import threading
import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config, notifications
from .database import SessionLocal, ensure_columns, engine, get_db
from . import clustering, stories as story_logic
from .enrichment import enrich_article, enrich_pending_articles
from .ingestion import add_missing_default_feeds, ingest_all
from .models import Article, Base, Feed
from .schemas import (ArticleDetail, ArticlePage, StoryDetail, StoryPage, Digest, DigestItem,
                      FeedCreate, FeedOut, FeedIngestResult, IngestResult,
                      Stats, TrendingStory)
from .quality import backfill_info_scores
from .seed_data import backfill_keywords, seed_if_empty

logger = logging.getLogger("signaldesk")

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
FRONTEND_DIR = BASE_DIR.parent / "frontend"

INGEST_INTERVAL_MINUTES = config.INGEST_INTERVAL_MINUTES
_started_at = time.time()
_ingest_lock = threading.Lock()  # prevents overlapping ingestion runs
_ingest_last_finished = 0.0


async def _scheduled_ingestion():
    """Auto-pilot: periodically run the ingestion pipeline in the background."""
    from .database import SessionLocal as _SL

    first_run = True
    while True:
        wait = 30 if first_run else INGEST_INTERVAL_MINUTES * 60
        first_run = False
        await asyncio.sleep(wait)
        try:
            with _SL() as db:
                feeds = [
                    {"name": f.name, "url": f.url}
                    for f in db.execute(select(Feed).where(Feed.is_active)).scalars().all()
                ]
                feed_rows = {f.name: f for f in db.execute(select(Feed)).scalars().all()}
                results = ingest_all(db, feeds, feed_rows=feed_rows)
                added = sum(r["added"] for r in results)
                logger.info("[scheduler] auto-ingest finished: +%s new articles", added)
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
                digest = compute_digest(db)
            result = notifications.deliver_digest(digest)
            logger.info("[digest] scheduled delivery: sent=%s errors=%s",
                        result["sent"], result["errors"])
        except Exception:  # noqa: BLE001
            logger.exception("[digest] scheduled delivery failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("[boot] SignalDesk v%s (%s)", config.VERSION, config.APP_ENV)
    Base.metadata.create_all(bind=engine)
    ensure_columns()
    with SessionLocal() as db:
        seeded = seed_if_empty(db, live=not config.SCHEDULER_DISABLED)
        if seeded:
            logger.info("[seed] First boot: populated %s articles", seeded)
        backfilled = backfill_keywords(db)
        if backfilled:
            logger.info("[migrate] Backfilled keywords for %s articles", backfilled)
        scores = backfill_info_scores(db)
        if scores["scored"]:
            logger.info("[migrate] Scored %s articles for information quality", scores["scored"])
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


def require_api_token(request: Request) -> None:
    """Protect state-changing endpoints when API_TOKEN is configured.

    Accepts either `X-API-Key: <token>` or `Authorization: Bearer <token>`.
    Read-only endpoints stay public so the dashboard can render before login.
    """
    if not config.API_TOKEN:
        return
    supplied = request.headers.get("x-api-key", "")
    if not supplied:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            supplied = auth[7:].strip()
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
        return FileResponse(DIST_DIR / "index.html", headers=_NO_CACHE)
else:
    @app.get("/", include_in_schema=False)
    def index_missing():
        return HTMLResponse(
            "<h1>SignalDesk API is running</h1>"
            "<p>The dashboard hasn't been built yet. Run <code>cd frontend &amp;&amp; npm install "
            "&amp;&amp; npm run build</code>, or <code>npm run dev</code> for development. "
            "API docs: <a href='/docs'>/docs</a></p>",
            status_code=200,
        )


# --------------------------------------------------------------------------- #
# Health & stats
# --------------------------------------------------------------------------- #

@app.get("/api/health", tags=["System"])
def health(db: Session = Depends(get_db)):
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
    return {"required": bool(config.API_TOKEN)}


@app.get("/api/stats", response_model=Stats, tags=["System"])
def stats(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(Article)) or 0
    if total == 0:
        return Stats(total_articles=0, total_sources=0, avg_sentiment=0.0,
                     ingested_last_24h=0, positive=0, neutral=0, negative=0,
                     topic_breakdown={}, sentiment_7d=[])

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    ingested_24h = db.scalar(
        select(func.count()).select_from(Article)
        .where(Article.published_at >= day_ago)) or 0
    avg_sentiment = db.scalar(select(func.coalesce(func.avg(Article.sentiment), 0.0))) or 0.0

    sentiments = [s for (s,) in db.execute(select(Article.sentiment)).all()]
    positive = sum(1 for s in sentiments if s > 0.15)
    negative = sum(1 for s in sentiments if s < -0.15)
    neutral = total - positive - negative

    topics = Counter(t for (t,) in db.execute(select(Article.topic)).all())

    # Daily average sentiment for the last 7 days (for the trend chart)
    rows = db.execute(
        select(Article.published_at, Article.sentiment)
        .where(Article.published_at >= week_ago)
    ).all()
    buckets: dict[str, list[float]] = {}
    for published, sentiment in rows:
        if published is None:
            continue
        day = published.astimezone(timezone.utc).strftime("%Y-%m-%d")
        buckets.setdefault(day, []).append(sentiment)
    sentiment_7d = [
        {"date": day, "avg_sentiment": round(sum(vals) / len(vals), 3), "count": len(vals)}
        for day, vals in sorted(buckets.items())
    ]

    return Stats(
        total_articles=total,
        total_sources=db.scalar(select(func.count(func.distinct(Article.source)))) or 0,
        avg_sentiment=round(avg_sentiment, 3),
        ingested_last_24h=ingested_24h,
        positive=positive, neutral=neutral, negative=negative,
        topic_breakdown=dict(topics.most_common()),
        sentiment_7d=sentiment_7d,
    )


# --------------------------------------------------------------------------- #
# Articles
# --------------------------------------------------------------------------- #

@app.get("/api/trending", response_model=list[TrendingStory], tags=["Intelligence"])
def trending_stories(limit: int = Query(clustering.HOT_STORIES, ge=1, le=20), db: Session = Depends(get_db)):
    """Hot topics: the stories the most outlets are covering right now."""
    return clustering.trending(db, limit)


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
    db: Session = Depends(get_db),
):
    """Flat list: every report on its own row."""
    q, order = _filtered(db, search, source, topic, sentiment, cluster, hot, ids, order)
    total = story_logic.count_matching(db, q)
    q = q.order_by(*story_logic.ordering(order))
    items = db.execute(q.offset(offset).limit(limit)).scalars().all()
    clustering.annotate(db, items)
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
    db: Session = Depends(get_db),
):
    """Grouped list: one card per event, the best-informed report leading it."""
    q, order = _filtered(db, search, source, topic, sentiment, cluster, hot, ids, order)
    ordered = db.execute(q.with_only_columns(Article.id).order_by(*story_logic.ordering(order))).scalars().all()
    page = story_logic.build_page(db, list(ordered), offset, limit)
    return StoryPage(total=page["total"], article_total=page["article_total"],
                     items=page["stories"], offset=offset, limit=limit)


def _cluster_or_404(db: Session, cluster_id: int):
    _, by_id = clustering.get_clusters(db)
    cluster = by_id.get(cluster_id)
    if cluster is None:
        raise HTTPException(404, "Story not found. It may have aged out or merged into another story.")
    return cluster


@app.get("/api/stories/{cluster_id}", response_model=StoryDetail, tags=["Articles"])
def story_detail(cluster_id: int, db: Session = Depends(get_db)):
    """One story in depth: its brief, how the outlets compare, and every report ranked."""
    return story_logic.story_detail(db, _cluster_or_404(db, cluster_id))


@app.post("/api/stories/{cluster_id}/brief", response_model=StoryDetail, tags=["Articles"],
          dependencies=[Depends(require_api_token)])
def refresh_story_brief(cluster_id: int, db: Session = Depends(get_db)):
    """Rewrite the story brief now (uses the language model when one is configured)."""
    return story_logic.story_detail(db, _cluster_or_404(db, cluster_id), force_brief=True)


@app.get("/api/articles/export.csv", tags=["Articles"])
def export_articles_csv(
    db: Session = Depends(get_db),
):
    """Export all articles as CSV (respecting the same filters as /api/articles)."""
    import csv
    import io

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
def get_article(article_id: int, db: Session = Depends(get_db)):
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(404, "Article not found")
    return _with_related(db, article)


def _with_related(db: Session, article: Article) -> Article:
    """Annotate an article with its story cluster and the other coverage of it."""
    clustering.annotate(db, [article])
    others = []
    if article.cluster_id:
        _, by_id = clustering.get_clusters(db)
        ids = [i for i in by_id[article.cluster_id].article_ids if i != article.id]
        # best-informed report first, so "Also covered by" is ranked, not just chronological
        others = story_logic.ranked(db.execute(select(Article).where(Article.id.in_(ids))).scalars().all())
    article.related = others
    return article


@app.post("/api/articles/{article_id}/summarize", response_model=ArticleDetail,
          tags=["Articles"], dependencies=[Depends(require_api_token)])
def summarize_article(article_id: int, db: Session = Depends(get_db)):
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
def daily_digest(db: Session = Depends(get_db)):
    """A generated intelligence brief: recent signals, extremes, and a headline."""
    return compute_digest(db)


@app.post("/api/digest/send", tags=["Intelligence"],
          dependencies=[Depends(require_api_token)])
def send_digest(db: Session = Depends(get_db)):
    """Deliver the daily brief to every configured channel (Slack/email)."""
    if not notifications.configured_channels():
        raise HTTPException(
            400,
            "No digest channel configured — set SLACK_WEBHOOK_URL or "
            "DIGEST_EMAILS + SMTP_HOST.",
        )
    result = notifications.deliver_digest(compute_digest(db))
    if not result["sent"]:
        raise HTTPException(502, f"Digest delivery failed: {result['errors']}")
    return result


def compute_digest(db: Session) -> Digest:
    """Build the daily brief. Shared by the API, the scheduler, and delivery."""
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    recent = db.execute(
        select(Article).where(Article.published_at >= day_ago).order_by(Article.published_at.desc())
    ).scalars().all()

    window = "Last 24 hours"
    if not recent:
        recent = db.execute(select(Article).order_by(Article.published_at.desc().nullslast()).limit(50)).scalars().all()
        window = "Most recent signals"

    if not recent:
        return Digest(
            generated_at=now, window_label=window, total_articles=0, articles_last_24h=0,
            avg_sentiment=0.0, headline="No signals ingested yet — run Ingest Feeds.",
            topic_breakdown={}, top_positive=[], top_negative=[],
        )

    avg = round(sum(a.sentiment for a in recent) / len(recent), 3)
    if avg > 0.15:
        tone = "mostly positive wording"
    elif avg < -0.15:
        tone = "mostly negative wording"
    else:
        tone = "a mix of positive and negative wording"

    topics = Counter(a.topic for a in recent)
    lead_topic = topics.most_common(1)[0][0] if topics else "General"
    headline = (
        f"{len(recent)} signals in the last 24h — overall {tone} (average score {avg:+.2f}). "
        f"Hottest topic: {lead_topic}."
    )

    def to_item(a: Article) -> DigestItem:
        return DigestItem(id=a.id, title=a.title, source=a.source,
                          sentiment=a.sentiment, topic=a.topic, url=a.url)

    top_positive = [to_item(a) for a in sorted(recent, key=lambda x: -x.sentiment)[:3]
                    if a.sentiment > 0.15]
    top_negative = [to_item(a) for a in sorted(recent, key=lambda x: x.sentiment)[:3]
                    if a.sentiment < -0.15]

    return Digest(
        generated_at=now,
        window_label=window,
        total_articles=db.scalar(select(func.count()).select_from(Article)) or 0,
        articles_last_24h=len(recent),
        avg_sentiment=avg,
        headline=headline,
        topic_breakdown=dict(topics.most_common()),
        top_positive=top_positive,
        top_negative=top_negative,
    )


# --------------------------------------------------------------------------- #
# Feeds & ingestion
# --------------------------------------------------------------------------- #

@app.get("/api/feeds", response_model=list[FeedOut], tags=["Feeds"])
def list_feeds(db: Session = Depends(get_db)):
    return db.execute(select(Feed).order_by(Feed.name)).scalars().all()


@app.post("/api/feeds", response_model=FeedOut, status_code=201, tags=["Feeds"],
          dependencies=[Depends(require_api_token)])
def create_feed(body: FeedCreate, db: Session = Depends(get_db)):
    from urllib.parse import urlparse

    parsed = urlparse(str(body.url))
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(422, "Feed URL must be an http(s) URL")
    feed = Feed(name=body.name.strip(), url=str(body.url))
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
def add_default_feeds(db: Session = Depends(get_db)):
    """Add the recommended feeds that are missing. Returns only the newly added ones."""
    return add_missing_default_feeds(db)


@app.delete("/api/feeds/{feed_id}", status_code=204, tags=["Feeds"],
            dependencies=[Depends(require_api_token)])
def delete_feed(feed_id: int, db: Session = Depends(get_db)):
    feed = db.get(Feed, feed_id)
    if not feed:
        raise HTTPException(404, "Feed not found")
    db.delete(feed)
    db.commit()


@app.post("/api/ingest", response_model=IngestResult, tags=["Ingestion"],
          dependencies=[Depends(require_api_token)])
def ingest(db: Session = Depends(get_db), background_tasks: BackgroundTasks = None):
    """Fetch every active RSS feed, dedupe by URL, analyze, and store new articles.

    Full-text enrichment (fetching the linked pages and writing clean
    summaries) runs in the background right after the response.
    """
    global _ingest_last_finished

    # One ingestion at a time, plus a cooldown so rapid clicking can't
    # hammer every configured RSS origin.
    if _ingest_lock.locked() or time.time() - _ingest_last_finished < config.INGEST_COOLDOWN_SECONDS:
        raise HTTPException(
            429,
            "An ingestion just ran — give the feeds a moment before refreshing again.",
        )
    with _ingest_lock:
        feed_rows = {f.name: f for f in db.execute(select(Feed).where(Feed.is_active)).scalars().all()}
        feeds = [{"name": f.name, "url": f.url} for f in feed_rows.values()]
        started = time.perf_counter()
        results = ingest_all(db, feeds, feed_rows=feed_rows)
        duration = time.perf_counter() - started
        _ingest_last_finished = time.time()

    pending = db.scalar(
        select(func.count()).select_from(Article).where(
            Article.enriched_at.is_(None), Article.is_seed.is_(False))
    ) or 0
    missing_images = db.scalar(
        select(func.count()).select_from(Article).where(
            Article.image_url.is_(None), Article.is_seed.is_(False))
    ) or 0
    if background_tasks and (pending or missing_images):
        background_tasks.add_task(_enrich_background)

    return IngestResult(
        added=sum(r["added"] for r in results),
        fetched=sum(r["fetched"] for r in results),
        skipped=sum(r["skipped"] for r in results),
        results=[FeedIngestResult(**r) for r in results],
        duration_seconds=round(duration, 2),
        enrich_queued=pending,
    )


def _enrich_background():
    """Background worker: enrich pending articles with full-text summaries."""
    with SessionLocal() as db:
        try:
            # Keep going wave by wave so a big ingest (many feeds) is fully enriched,
            # but stop if a wave makes no progress.
            for _ in range(12):
                stats = enrich_pending_articles(db)
                logger.info("[enrich] deep summaries generated for %s articles (%s remaining)",
                            stats["enriched"], stats["remaining"])
                if not stats["enriched"] or not stats["remaining"]:
                    break
        except Exception:  # noqa: BLE001
            logger.exception("[enrich] enrichment failed")
