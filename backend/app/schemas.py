"""Pydantic schemas for API requests/responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ArticleOut(BaseModel):
    """An article as listed in the feed."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    url: str
    source: str
    summary: str | None
    summary_deep: str | None = None
    keywords: str | None = None
    image_url: str | None = None
    info_score: float | None = None  # 0-100, how much real information this report carries
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
    """A compact article shown as another report of the same story."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source: str
    url: str
    published_at: datetime | None
    sentiment: float = 0.0
    info_score: float | None = None
    summary: str | None = None
    summary_deep: str | None = None


class ArticleDetail(ArticleOut):
    """An article with its full analysis and related reports."""
    related: list[RelatedArticle] = []  # other coverage of the same story
    full_text: str | None = None  # extracted page text for the reader view
    summary_structured: str | None = None  # skimmable sections (## heading / - bullet)
    enriched_at: datetime | None = None
    analysis_model: str | None = None


class ReportBrief(BaseModel):
    """A report shown under its story's lead, best-informed first."""
    id: int
    title: str
    source: str
    url: str
    published_at: datetime | None
    sentiment: float
    info_score: float | None = None
    summary: str | None = None
    image_url: str | None = None


class Story(BaseModel):
    """One event: the best-informed report plus the other outlets' reports."""
    model_config = ConfigDict(from_attributes=True)

    key: str  # "c<cluster id>" or "a<article id>" for a story with a single report
    cluster_id: int | None
    lead: ArticleOut
    others: list[ReportBrief]
    report_count: int
    outlets: int
    sources: list[str]
    best_score: float | None
    watch_matches: list[str] = []  # watchlist terms this story matches


class StoryPage(BaseModel):
    """A page of stories."""
    total: int  # stories
    article_total: int  # individual reports behind them
    items: list[Story]
    offset: int
    limit: int


class OutletStat(BaseModel):
    """One outlet's standing within a story."""
    source: str
    report_id: int
    title: str
    info_score: float | None
    sentiment: float
    chars: int
    numbers: int  # figures called out in the report's "By the numbers"
    quotes: int
    published_at: datetime | None
    badges: list[str] = []
    reliability: int | None = None  # the outlet's source-signals score, when there is enough data
    reliability_label: str | None = None


class StoryBriefOut(BaseModel):
    """A story brief: what the outlets agree on and where they differ."""
    kind: str  # "ai" (written by the configured model) or "auto" (extractive fallback)
    headline: str
    agree: list[str]
    differ: list[str]
    model: str | None = None
    generated_at: datetime | None = None


class ClaimOut(BaseModel):
    """One factual claim and how the outlets treat it."""
    text: str
    status: str  # agreed | disputed | single
    outlets: list[str]
    values: dict[str, str] | None = None  # each outlet's figure, for disputed claims


class ClaimsOut(BaseModel):
    """The claim-level comparison of a story."""
    kind: str = "auto"  # "ai" (model) or "auto" (extractive fallback)
    items: list[ClaimOut] = []


class ScoreComponent(BaseModel):
    """One part of a source's signals score, with its working."""
    key: str
    label: str
    points: float | None  # None when there is not enough evidence yet
    max: int
    detail: str


class CorrectionsOut(BaseModel):
    """How often an outlet's pages carry correction notices."""
    notices: int = 0
    rate: float = 0.0
    policy: bool = False


class SourceProfile(BaseModel):
    """An evidence-based profile of one outlet (not an editorial rating)."""
    source: str
    articles: int
    score: int | None
    label: str
    breakdown: list[ScoreComponent]
    corroboration_rate: float
    first_report_rate: float | None = None
    corrections: CorrectionsOut = CorrectionsOut()


class SourceList(BaseModel):
    """All outlet profiles with the standing disclaimer."""
    note: str
    window_days: int
    items: list[SourceProfile]


class StoryDetail(BaseModel):
    """A story with its ranked reports, outlet comparison and brief."""
    cluster_id: int
    title: str
    report_count: int
    outlets: int
    avg_sentiment: float
    sentiment_spread: float
    reports: list[ReportBrief]  # best-informed first
    comparison: list[OutletStat]
    brief: StoryBriefOut
    claims: ClaimsOut = ClaimsOut()


class ArticlePage(BaseModel):
    """A page of articles with the total count."""
    total: int
    items: list[ArticleOut]
    offset: int
    limit: int


class FeedOut(BaseModel):
    """A feed as returned by the API."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    is_active: bool
    shared: bool = True  # part of the shared base data (a visitor cannot remove it) rather than their own
    last_fetched_at: datetime | None = None
    last_status: str | None = None


class FeedCreate(BaseModel):
    """Request body for adding a feed."""
    name: str = Field(min_length=1, max_length=200)
    url: HttpUrl


class FeedIngestResult(BaseModel):
    """Per-feed result of an ingest run."""
    feed: str
    fetched: int
    added: int
    skipped: int
    error: str | None = None


class WatchIn(BaseModel):
    """Request body for creating a watch."""
    term: str = Field(min_length=1, max_length=100)
    topic: str | None = Field(default=None, max_length=50)
    min_outlets: int = Field(default=2, ge=1, le=10)


class WatchPatch(BaseModel):
    """Request body for pausing or resuming a watch."""
    is_active: bool


class WatchOut(BaseModel):
    """A watch as returned by the API, with its current match count."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    term: str
    topic: str | None
    min_outlets: int
    is_active: bool
    created_at: datetime
    matches: int = 0  # stories matching it right now


class WatchAlertOut(BaseModel):
    """An alert raised when a story matched a watch."""
    watch_id: int
    term: str
    story_key: str
    cluster_id: int | None
    article_id: int
    title: str
    outlets: int
    reports: int


class IngestResult(BaseModel):
    """Result of an ingest run across all feeds."""
    added: int
    fetched: int
    skipped: int
    results: list[FeedIngestResult]
    duration_seconds: float
    enrich_queued: int = 0
    alerts: list[WatchAlertOut] = []  # watchlist stories that newly matched


class TrendingStory(BaseModel):
    """A story covered by several outlets right now."""
    cluster_id: int
    article_id: int  # the representative report, for "open this story"
    title: str
    reports: int
    outlets: int
    sources: list[str]
    topic: str
    avg_sentiment: float
    latest_at: datetime
    first_seen: datetime | None = None  # when the event was first covered, if it is tracked
    days_active: int = 1


class TimelineDay(BaseModel):
    """One day of an event's coverage."""
    date: str
    reports: int
    outlets: int
    new_outlets: list[str]
    avg_sentiment: float | None = None
    headline: str | None = None


class StoryTimeline(BaseModel):
    """How coverage of an event developed day by day."""
    event_id: int | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    days_active: int = 0
    reports: int = 0
    outlets: int = 0
    peak_reports: int = 0
    sentiment_shift: float = 0.0  # tone on the last day minus the first
    first_reported_by: str | None = None
    days: list[TimelineDay] = []


class Stats(BaseModel):
    """Dashboard statistics."""
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
    """One article listed in the daily brief."""
    id: int
    title: str
    source: str
    sentiment: float
    topic: str
    url: str


class Digest(BaseModel):
    """The daily brief."""
    generated_at: datetime
    window_label: str
    total_articles: int
    articles_last_24h: int
    avg_sentiment: float
    headline: str
    topic_breakdown: dict[str, int]
    top_positive: list[DigestItem]
    top_negative: list[DigestItem]
