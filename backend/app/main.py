"""SignalDesk — AI-powered news intelligence dashboard.

FastAPI application: REST API + static dashboard frontend.

Run locally:
    uvicorn app.main:app --reload   (from the backend/ directory)
"""

import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import SessionLocal, engine, get_db
from .ingestion import ingest_all
from .models import Article, Base, Feed
from .schemas import (ArticlePage, FeedCreate, FeedOut, IngestResult,
                      FeedIngestResult, Stats)
from .seed_data import seed_if_empty

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
FRONTEND_DIR = BASE_DIR.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seeded = seed_if_empty(db)
        if seeded:
            print(f"[seed] Seeded database with {seeded} demo articles")
    yield


app = FastAPI(
    title="SignalDesk API",
    description="Automated news research platform: RSS ingestion, AI analysis, intelligence dashboard.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
    sentiment: str | None = Query(None, pattern="^(positive|neutral|negative)$"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
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

    q = q.order_by(Article.published_at.desc().nullslast(), Article.id.desc())
    items = db.execute(q.offset(offset).limit(limit)).scalars().all()
    return ArticlePage(total=total, items=items, offset=offset, limit=limit)


@app.get("/api/articles/{article_id}", tags=["Articles"])
def get_article(article_id: int, db: Session = Depends(get_db)):
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(404, "Article not found")
    return article


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
    feeds = [
        {"name": f.name, "url": f.url}
        for f in db.execute(select(Feed).where(Feed.is_active)).scalars().all()
    ]
    started = time.perf_counter()
    results = ingest_all(db, feeds)
    duration = time.perf_counter() - started
    return IngestResult(
        added=sum(r["added"] for r in results),
        fetched=sum(r["fetched"] for r in results),
        skipped=sum(r["skipped"] for r in results),
        results=[FeedIngestResult(**r) for r in results],
        duration_seconds=round(duration, 2),
    )
