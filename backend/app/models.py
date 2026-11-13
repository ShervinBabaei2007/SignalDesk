"""SQLAlchemy models for SignalDesk."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Article(Base):
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
        if self.sentiment > 0.15:
            return "positive"
        if self.sentiment < -0.15:
            return "negative"
        return "neutral"

    @property
    def keyword_list(self) -> list[str]:
        return [k.strip() for k in (self.keywords or "").split(",") if k.strip()]


class Feed(Base):
    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(300), nullable=True)
