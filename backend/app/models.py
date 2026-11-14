"""SQLAlchemy models for SignalDesk."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from . import sentiment as sentiment_scale
from .database import Base


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class Article(Base):
    """A news article with its analysis (sentiment, topic, summaries, information score)."""
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # from RSS feed
    summary_deep: Mapped[str | None] = mapped_column(Text, nullable=True)  # TL;DR from full text
    summary_structured: Mapped[str | None] = mapped_column(Text, nullable=True)  # skimmable sections
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # extracted page text
    keywords: Mapped[str | None] = mapped_column(String(500), nullable=True)  # comma-separated
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # lead image from the real page
    info_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)  # 0-100, see quality.py
    why_it_matters: Mapped[str | None] = mapped_column(Text, nullable=True)  # LLM significance note
    importance: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..10
    relevance: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..10
    content_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    analysis_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    analysis_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # llm | lexicon
    topic: Mapped[str] = mapped_column(String(50), default="General", index=True)
    sentiment: Mapped[float] = mapped_column(Float, default=0.0)  # -1.0 .. +1.0
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def sentiment_label(self) -> str:
        """Sentiment as 'positive', 'neutral' or 'negative'."""
        return sentiment_scale.label(self.sentiment)

    @property
    def keyword_list(self) -> list[str]:
        """Comma-separated keywords as a list."""
        return [k.strip() for k in (self.keywords or "").split(",") if k.strip()]


class Feed(Base):
    """An RSS feed source with its health status."""
    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(300), nullable=True)


class StoryBrief(Base):
    """Cached "what everyone agrees on / where they differ" for one story.

    Rewritten only when the story's reports change (`member_hash`)."""
    __tablename__ = "story_briefs"

    cluster_id: Mapped[int] = mapped_column(primary_key=True)
    member_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON: kind, headline, agree, differ, model
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Watch(Base):
    """A term to watch for: alerts when a story matching it is covered by enough outlets."""
    __tablename__ = "watches"

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(100), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(50), nullable=True)
    min_outlets: Mapped[int] = mapped_column(Integer, default=2)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WatchAlert(Base):
    """Remembers that a watch already fired for a story, so it never alerts twice."""
    __tablename__ = "watch_alerts"
    __table_args__ = (UniqueConstraint("watch_id", "story_key", name="uq_watch_story"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    watch_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    story_key: Mapped[str] = mapped_column(String(32), nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)  # delivered to Slack/email
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
