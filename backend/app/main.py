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
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config, notifications
from .database import SessionLocal, ensure_columns, engine, get_db
from .enrichment import enrich_article, enrich_pending_articles
from .ingestion import ingest_all
from .models import Article, Base, Feed
from .schemas import (ArticleDetail, ArticlePage, Digest, DigestItem,
                      FeedCreate, FeedOut, FeedIngestResult, IngestResult,
                      Stats)
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

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")


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
        {"date": day, "avg_sentiment": round(sum(vals) / len(vals), 3)}
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

@app.get("/api/articles", response_model=ArticlePage, tags=["Articles"])
def list_articles(
    search: str | None = Query(None, max_length=200),
    source: str | None = Query(None, max_length=200),
    topic: str | None = Query(None, max_length=50),
    sentiment: str | None = Query(None),
    order: str = Query("newest"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    # Tolerate empty query strings (?sentiment=) from clients
    sentiment = (sentiment or "").strip() or None
    source = (source or "").strip() or None
    topic = (topic or "").strip() or None
    search = (search or "").strip() or None
    order = (order or "newest").strip().lower()
    if sentiment and sentiment not in ("positive", "neutral", "negative"):
        raise HTTPException(422, "sentiment must be positive, neutral, or negative")
    if order not in ("newest", "oldest", "sentiment_high", "sentiment_low"):
        raise HTTPException(422, "order must be newest, oldest, sentiment_high, or sentiment_low")
    q = select(Article)
    if search:
        like = f"%{search}%"
        q = q.where(Article.title.ilike(like) | Article.summary.ilike(like))
    if source:
        q = q.where(Article.source == source)
    if topic:
        q = q.where(Article.topic == topic)

    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0

    if sentiment == "positive":
        q = q.where(Article.sentiment > 0.15)
    elif sentiment == "negative":
        q = q.where(Article.sentiment < -0.15)
    elif sentiment == "neutral":
        q = q.where(Article.sentiment >= -0.15, Article.sentiment <= 0.15)

    orderings = {
        "newest": (Article.published_at.desc().nullslast(), Article.id.desc()),
        "oldest": (Article.published_at.asc().nullslast(), Article.id.asc()),
        "sentiment_high": (Article.sentiment.desc(), Article.id.desc()),
        "sentiment_low": (Article.sentiment.asc(), Article.id.desc()),
    }
    q = q.order_by(*orderings[order])
    items = db.execute(q.offset(offset).limit(limit)).scalars().all()
    return ArticlePage(total=total, items=items, offset=offset, limit=limit)


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
    return article


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
        tone = "predominantly positive"
    elif avg < -0.15:
        tone = "predominantly negative"
    else:
        tone = "broadly mixed"

    topics = Counter(a.topic for a in recent)
    lead_topic = topics.most_common(1)[0][0] if topics else "General"
    headline = (
        f"{len(recent)} signals in the last 24h — sentiment {avg:+.2f} ({tone}). "
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
            stats = enrich_pending_articles(db)
            logger.info("[enrich] deep summaries generated for %s articles (%s remaining)",
                        stats["enriched"], stats["remaining"])
        except Exception:  # noqa: BLE001
            logger.exception("[enrich] enrichment failed")
