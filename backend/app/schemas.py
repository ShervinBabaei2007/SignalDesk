"""Pydantic schemas for API requests/responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    url: str
    source: str
    summary: str | None
    summary_deep: str | None = None
    keywords: str | None = None
    topic: str
    sentiment: float
    sentiment_label: str
    published_at: datetime | None
    ingested_at: datetime


class ArticleDetail(ArticleOut):
    is_seed: bool
    enriched_at: datetime | None = None


class ArticlePage(BaseModel):
    total: int
    items: list[ArticleOut]
    offset: int
    limit: int


class FeedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    is_active: bool
    last_fetched_at: datetime | None = None
    last_status: str | None = None


class FeedCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: HttpUrl


class FeedIngestResult(BaseModel):
    feed: str
    fetched: int
    added: int
    skipped: int
    error: str | None = None


class IngestResult(BaseModel):
    added: int
    fetched: int
    skipped: int
    results: list[FeedIngestResult]
    duration_seconds: float
    enrich_queued: int = 0


class Stats(BaseModel):
    total_articles: int
    total_sources: int
    avg_sentiment: float
    ingested_last_24h: int
    positive: int
    neutral: int
    negative: int
    topic_breakdown: dict[str, int]
    sentiment_7d: list[dict]


class DigestItem(BaseModel):
    id: int
    title: str
    source: str
    sentiment: float
    topic: str
    url: str


class Digest(BaseModel):
    generated_at: datetime
    window_label: str
    total_articles: int
    articles_last_24h: int
    avg_sentiment: float
    headline: str
    topic_breakdown: dict[str, int]
    top_positive: list[DigestItem]
    top_negative: list[DigestItem]
