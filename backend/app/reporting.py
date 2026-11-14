"""Reporting: the numbers the dashboard and the daily brief are built from.

``stats`` feeds the dashboard cards and the 7-day sentiment trend; ``digest``
builds the daily brief that the API, the scheduler and Slack/email delivery all
share. Both return typed results, so they are testable without HTTP.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import sentiment as sentiment_scale
from .models import Article
from .schemas import Digest, DigestItem, Stats

DAY = timedelta(hours=24)


def stats(db: Session) -> Stats:
    """Dashboard numbers: totals, sentiment counts, topic breakdown and the 7-day trend."""
    total = db.scalar(select(func.count()).select_from(Article)) or 0
    if total == 0:
        return Stats(total_articles=0, total_sources=0, avg_sentiment=0.0,
                     ingested_last_24h=0, positive=0, neutral=0, negative=0,
                     topic_breakdown={}, sentiment_7d=[])

    now = datetime.now(timezone.utc)
    day_ago = now - DAY
    week_ago = now - timedelta(days=7)

    ingested_24h = db.scalar(
        select(func.count()).select_from(Article)
        .where(Article.published_at >= day_ago)) or 0
    avg_sentiment = db.scalar(select(func.coalesce(func.avg(Article.sentiment), 0.0))) or 0.0

    by_label = sentiment_scale.counts(s for (s,) in db.execute(select(Article.sentiment)).all())

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
        positive=by_label["positive"], neutral=by_label["neutral"], negative=by_label["negative"],
        topic_breakdown=dict(topics.most_common()),
        sentiment_7d=sentiment_7d,
    )


def digest(db: Session) -> Digest:
    """Build the daily brief. Shared by the API, the scheduler, and delivery."""
    now = datetime.now(timezone.utc)
    day_ago = now - DAY
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
    tone = sentiment_scale.tone(avg)

    topics = Counter(a.topic for a in recent)
    lead_topic = topics.most_common(1)[0][0] if topics else "General"
    headline = (
        f"{len(recent)} signals in the last 24h — overall {tone} (average score {avg:+.2f}). "
        f"Hottest topic: {lead_topic}."
    )

    def to_item(a: Article) -> DigestItem:
        """Convert an article into a compact digest item."""
        return DigestItem(id=a.id, title=a.title, source=a.source,
                          sentiment=a.sentiment, topic=a.topic, url=a.url)

    top_positive = [to_item(a) for a in sorted(recent, key=lambda x: -x.sentiment)[:3]
                    if sentiment_scale.label(a.sentiment) == "positive"]
    top_negative = [to_item(a) for a in sorted(recent, key=lambda x: x.sentiment)[:3]
                    if sentiment_scale.label(a.sentiment) == "negative"]

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
