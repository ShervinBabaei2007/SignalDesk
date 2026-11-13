"""SignalDesk — AI-powered news intelligence dashboard.

FastAPI application: REST API + static dashboard frontend.

Run locally:
    uvicorn app.main:app --reload   (from the backend/ directory)
"""

import asyncio
import logging
import os
import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import SessionLocal, ensure_columns, engine, get_db
from .ingestion import ingest_all
from .models import Article, Base, Feed
from .schemas import (ArticleDetail, ArticlePage, Digest, DigestItem,
                      FeedCreate, FeedOut, FeedIngestResult, IngestResult,
                      Stats)
from .seed_data import backfill_keywords, seed_if_empty

logger = logging.getLogger("signaldesk")

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
FRONTEND_DIR = BASE_DIR.parent / "frontend"

INGEST_INTERVAL_MINUTES = int(os.getenv("INGEST_INTERVAL_MINUTES", "30"))


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    Base.metadata.create_all(bind=engine)
    ensure_columns()
    with SessionLocal() as db:
        seeded = seed_if_empty(db)
        if seeded:
            print(f"[seed] Seeded database with {seeded} demo articles")
        backfilled = backfill_keywords(db)
        if backfilled:
            logger.info("[migrate] Backfilled keywords for %s articles", backfilled)
    scheduler_task = None
    if INGEST_INTERVAL_MINUTES > 0 and not os.getenv("SCHEDULER_DISABLED"):
        scheduler_task = asyncio.create_task(_scheduled_ingestion())
        logger.info("[scheduler] auto-ingest every %s minutes", INGEST_INTERVAL_MINUTES)
    yield
    if scheduler_task:
        scheduler_task.cancel()


app = FastAPI(
    title="SignalDesk API",
    description="Automated news research platform: RSS ingestion, AI analysis, intelligence dashboard.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


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
        "articles": db.scalar(select(func.count()).select_from(Article)),
        "feeds": db.scalar(select(func.count()).select_from(Feed)),
    }


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


# --------------------------------------------------------------------------- #
# Digest
# --------------------------------------------------------------------------- #

@app.get("/api/digest", response_model=Digest, tags=["Intelligence"])
def daily_digest(db: Session = Depends(get_db)):
    """A generated intelligence brief: recent signals, extremes, and a headline."""
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


@app.post("/api/feeds", response_model=FeedOut, status_code=201, tags=["Feeds"])
def create_feed(body: FeedCreate, db: Session = Depends(get_db)):
    feed = Feed(name=body.name.strip(), url=str(body.url))
    db.add(feed)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "A feed with this name or URL already exists")
    db.refresh(feed)
    return feed


@app.delete("/api/feeds/{feed_id}", status_code=204, tags=["Feeds"])
def delete_feed(feed_id: int, db: Session = Depends(get_db)):
    feed = db.get(Feed, feed_id)
    if not feed:
        raise HTTPException(404, "Feed not found")
    db.delete(feed)
    db.commit()


@app.post("/api/ingest", response_model=IngestResult, tags=["Ingestion"])
def ingest(db: Session = Depends(get_db)):
    """Fetch every active RSS feed, dedupe by URL, analyze, and store new articles."""
    feed_rows = {f.name: f for f in db.execute(select(Feed).where(Feed.is_active)).scalars().all()}
    feeds = [{"name": f.name, "url": f.url} for f in feed_rows.values()]
    started = time.perf_counter()
    results = ingest_all(db, feeds, feed_rows=feed_rows)
    duration = time.perf_counter() - started
    return IngestResult(
        added=sum(r["added"] for r in results),
        fetched=sum(r["fetched"] for r in results),
        skipped=sum(r["skipped"] for r in results),
        results=[FeedIngestResult(**r) for r in results],
        duration_seconds=round(duration, 2),
    )
