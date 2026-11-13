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
    image_url: str | None = None
    why_it_matters: str | None = None
    importance: float | None = None
    relevance: float | None = None
    content_type: str | None = None
    analysis_source: str | None = None
    topic: str
    sentiment: float
    sentiment_label: str
    published_at: datetime | None
    ingested_at: datetime
    cluster_id: int | None = None  # shared by articles covering the same story
    cluster_size: int = 1  # articles in this story (1 = standalone)
    cluster_sources: list[str] = []  # distinct outlets covering it
    is_seed: bool = False  # demo articles have placeholder URLs — no real page to visit


class RelatedArticle(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source: str
    url: str
    published_at: datetime | None
    sentiment: float = 0.0
    summary: str | None = None
    summary_deep: str | None = None


class ArticleDetail(ArticleOut):
    related: list[RelatedArticle] = []  # other coverage of the same story
    full_text: str | None = None  # extracted page text for the reader view
    summary_structured: str | None = None  # skimmable sections (## heading / - bullet)
    enriched_at: datetime | None = None
    analysis_model: str | None = None


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


class TrendingStory(BaseModel):
    cluster_id: int
    article_id: int  # the representative report, for "open this story"
    title: str
    reports: int
    outlets: int
    sources: list[str]
    topic: str
    avg_sentiment: float
    latest_at: datetime


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
