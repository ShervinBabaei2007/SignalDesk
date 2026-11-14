"""SQLAlchemy models for SignalDesk."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

from . import sentiment as sentiment_scale
from .database import Base


# The shared base data (seeded and cron-ingested) belongs to no workspace; a visitor's own rows carry their id.
NO_WORKSPACE = ""


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class Article(Base):
    """A news article with its analysis (sentiment, topic, summaries, information score)."""
    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("workspace_id", "url", name="uq_article_workspace_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
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
    extraction: Mapped[str | None] = mapped_column(String(12), nullable=True)  # page | fallback (see enrichment)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)  # base64 float16 vector (see embeddings.py)
    embedding_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    workspace_id: Mapped[str] = mapped_column(String(40), default=NO_WORKSPACE, server_default=NO_WORKSPACE,
                                              nullable=False, index=True)

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
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_feed_workspace_name"),
                      UniqueConstraint("workspace_id", "url", name="uq_feed_workspace_url"))

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(40), default=NO_WORKSPACE, server_default=NO_WORKSPACE,
                                              nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(300), nullable=True)

    @property
    def shared(self) -> bool:
        """True for the shared base feeds, false for a visitor's own."""
        return self.workspace_id == NO_WORKSPACE


class StoryBrief(Base):
    """Cached "what everyone agrees on / where they differ" for one story.

    Rewritten only when the story's reports change (`member_hash`)."""
    __tablename__ = "story_briefs"

    cluster_id: Mapped[int] = mapped_column(primary_key=True)
    member_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON: kind, headline, agree, differ, model
    claims: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON claim comparison (see claims.py)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Watch(Base):
    """A term to watch for: alerts when a story matching it is covered by enough outlets."""
    __tablename__ = "watches"

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(100), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(50), nullable=True)
    min_outlets: Mapped[int] = mapped_column(Integer, default=2)
    workspace_id: Mapped[str] = mapped_column(String(40), default=NO_WORKSPACE, server_default=NO_WORKSPACE,
                                              nullable=False, index=True)
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


class PipelineRun(Base):
    """One ingest cycle of the shared data: how long it took and what it found (see :mod:`app.observability`)."""
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)  # manual | scheduled
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)  # false when the cycle itself crashed
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    feeds_ok: Mapped[int] = mapped_column(Integer, default=0)
    feeds_failed: Mapped[int] = mapped_column(Integer, default=0)
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    added: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    alerts: Mapped[int] = mapped_column(Integer, default=0)


class FeedRun(Base):
    """How one feed behaved in one cycle: whether it answered, how fast, and what it yielded."""
    __tablename__ = "feed_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    feed: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    added: Mapped[int] = mapped_column(Integer, default=0)


# --------------------------------------------------------------------------- #
# Workspace scoping
# --------------------------------------------------------------------------- #
# Every ORM SELECT on a session is narrowed to what that session's workspace may see, so the dozens
# of `select(Article)` calls across the app need no workspace argument. `session.info["workspace"]`
# holds the id (NO_WORKSPACE for the shared base data, which is what scheduled jobs and tests use):
#   * articles and feeds: the shared base data plus the workspace's own rows,
#   * watches: only the workspace's own (the shared base watchlist belongs to the owner).

@event.listens_for(Session, "do_orm_execute")
def _scope_to_workspace(state) -> None:
    """Add the workspace visibility filters to every SELECT."""
    if not state.is_select:
        return
    ws = state.session.info.get("workspace", NO_WORKSPACE)
    state.statement = state.statement.options(
        with_loader_criteria(Article, lambda c: (c.workspace_id == NO_WORKSPACE) | (c.workspace_id == ws),
                             include_aliases=True),
        with_loader_criteria(Feed, lambda c: (c.workspace_id == NO_WORKSPACE) | (c.workspace_id == ws),
                             include_aliases=True),
        with_loader_criteria(Watch, lambda c: c.workspace_id == ws, include_aliases=True),
    )
