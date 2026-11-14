"""RSS ingestion pipeline: fetch feeds, dedupe, analyze, store."""

import calendar
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape

import feedparser
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import config, netguard
from .analysis import analyze
from .extractor import clean_image_url
from .models import NO_WORKSPACE, Article, Feed
from .quality import information_score

logger = logging.getLogger("signaldesk.ingestion")

# Feeds sometimes date entries ahead of now (scheduled posts, wrong timezones); allow only small clock skew.
FUTURE_SKEW = timedelta(hours=1)


def clamp_future(published_at: datetime | None, now: datetime | None = None) -> datetime | None:
    """Return the fetch time instead of a publish date that is more than FUTURE_SKEW in the future."""
    now = now or datetime.now(timezone.utc)
    if published_at is not None and published_at.tzinfo is not None and published_at > now + FUTURE_SKEW:
        return now
    return published_at

DEFAULT_FEEDS = [
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "BBC Technology", "url": "https://feeds.bbci.co.uk/news/technology/rss.xml"},
    {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
    # Broad, reputable coverage across the topics SignalDesk classifies
    {"name": "NPR News", "url": "https://feeds.npr.org/1001/rss.xml"},
    {"name": "The Guardian", "url": "https://www.theguardian.com/world/rss"},
    {"name": "Politico", "url": "https://rss.politico.com/politics-news.xml"},
    {"name": "STAT News", "url": "https://www.statnews.com/feed/"},
    {"name": "BBC Science", "url": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"},
    {"name": "CNBC", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
    {"name": "ScienceDaily", "url": "https://www.sciencedaily.com/rss/all.xml"},
    {"name": "BBC Health", "url": "https://feeds.bbci.co.uk/news/health/rss.xml"},
]


def add_missing_default_feeds(db: Session) -> list[Feed]:
    """Insert any recommended feed that isn't stored yet (matched by URL or name).

    Idempotent, so it is safe to call from first-boot seeding and from the
    "Add recommended feeds" action on databases created with the older,
    shorter default list.
    """
    urls = set(db.execute(select(Feed.url)).scalars())
    names = set(db.execute(select(Feed.name)).scalars())
    added = []
    for spec in DEFAULT_FEEDS:
        if spec["url"] in urls or spec["name"] in names:
            continue
        feed = Feed(name=spec["name"], url=spec["url"])
        db.add(feed)
        added.append(feed)
    if added:
        db.commit()
        for feed in added:
            db.refresh(feed)
    return added


def _parse_published(entry) -> datetime | None:
    """Parse a feed entry's published date into an aware UTC datetime, or None."""
    for attr in ("published_parsed", "updated_parsed"):
        value = getattr(entry, attr, None)
        if value:
            try:
                return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
            except Exception:  # noqa: BLE001
                pass
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return parsedate_to_datetime(raw)
            except Exception:  # noqa: BLE001
                pass
    return None


def strip_feed_metadata(text: str) -> str:
    """Remove feed-provider metadata junk (e.g. Hacker News embeds)."""
    for marker in ("Article URL:", "Comments URL:", "Points:"):
        if marker in text:
            text = text.split(marker)[0]
    return text.strip()


def _entry_text(entry) -> str:
    """Best available text of a feed entry (content, summary or description) with tags stripped."""
    title = getattr(entry, "title", "") or ""
    body = ""
    if getattr(entry, "content", None):
        body = entry.content[0].get("value", "")
    elif getattr(entry, "description", None):
        body = entry.description
    elif getattr(entry, "summary", None):
        body = entry.summary
    # feedparser can leave HTML entities/links in text; keep it readable
    body = re.sub(r"<[^>]+>", " ", body)
    body = unescape(body)
    body = strip_feed_metadata(body)
    return f"{title}. {body}".strip()


def _entry_image(entry) -> str | None:
    """Thumbnail advertised by the RSS entry itself (media:*, image enclosure)."""
    candidates = []
    for key in ("media_thumbnail", "media_content"):
        for m in getattr(entry, key, None) or []:
            if isinstance(m, dict) and (key == "media_thumbnail" or "image" in (m.get("type") or "image")
                                        or m.get("medium") == "image"):
                candidates.append(m.get("url"))
    for enc in getattr(entry, "enclosures", None) or []:
        if (enc.get("type") or "").startswith("image"):
            candidates.append(enc.get("href") or enc.get("url"))
    for c in candidates:
        url = clean_image_url(c)
        if url:
            return url
    return None


def ingest_feed(
    db: Session,
    feed_url: str,
    feed_name: str,
    max_entries: int = 20,
    feed: Feed | None = None,
) -> dict:
    """Fetch a single RSS feed and store any new articles.

    Returns per-feed stats: fetched, added (new), skipped (duplicates/errors).
    When `feed` (a Feed row) is given, its health status is updated too.
    """
    stats = {"feed": feed_name, "fetched": 0, "added": 0, "skipped": 0}

    def _finish(status: str) -> None:
        """Record the feed's last fetch time and status when a Feed row was given."""
        if feed is not None:
            feed.last_fetched_at = datetime.now(timezone.utc)
            feed.last_status = status[:300]
            db.commit()

    workspace = db.info.get("workspace", NO_WORKSPACE)
    started = time.perf_counter()
    try:
        if workspace:  # a visitor's URL: fetch it ourselves so only public addresses are ever requested
            parsed = feedparser.parse(netguard.fetch(feed_url, max_bytes=2_000_000).content)
        else:
            parsed = feedparser.parse(feed_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Feed %s failed to parse: %s", feed_url, exc)
        stats["error"] = str(exc)
        _finish(f"error: {exc}")
        return stats

    stats["latency_ms"] = round((time.perf_counter() - started) * 1000)
    entries = (parsed.entries or [])[:max_entries]
    stats["fetched"] = len(entries)
    status = getattr(parsed, "status", None)
    if not entries and (getattr(parsed, "bozo", False) or (isinstance(status, int) and status >= 400)):
        # feedparser does not raise on a dead or broken feed, so surface it as a failure
        reason = f"HTTP {status}" if isinstance(status, int) and status >= 400 else str(getattr(parsed, "bozo_exception", "unreadable feed"))
        stats["error"] = reason[:300]
        _finish(f"error: {reason}")
        return stats
    room = None  # how many more articles this workspace may store
    if workspace:
        owned = db.scalar(select(func.count()).select_from(Article).where(Article.workspace_id == workspace)) or 0
        room = max(config.WORKSPACE_MAX_ARTICLES - owned, 0)

    for entry in entries:
        url = getattr(entry, "link", None)
        title = unescape(getattr(entry, "title", None) or "").strip()
        if not url or not title:
            stats["skipped"] += 1
            continue

        if db.scalar(select(Article.id).where(Article.url == url)):
            stats["skipped"] += 1
            continue
        if room is not None and stats["added"] >= room:
            stats["skipped"] += 1
            continue

        text = _entry_text(entry)
        published_at = clamp_future(_parse_published(entry))
        if config.MAX_ARTICLE_AGE_DAYS > 0 and published_at is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=config.MAX_ARTICLE_AGE_DAYS)
            if published_at < cutoff:
                stats["skipped"] += 1
                continue
        result = analyze(text)
        article = Article(
            title=title[:500],
            url=url[:1000],
            source=feed_name[:200],
            summary=result["summary"],
            keywords=", ".join(result["keywords"]),
            image_url=_entry_image(entry),
            topic=result["topic"],
            sentiment=result["sentiment"],
            analysis_source="lexicon",
            published_at=published_at,
            workspace_id=workspace,
        )
        article.info_score = information_score(article)
        db.add(article)
        try:
            db.commit()
            stats["added"] += 1
        except IntegrityError:
            db.rollback()
            stats["skipped"] += 1

    _finish(f"ok: {stats['added']} added, {stats['fetched']} fetched")
    return stats


def ingest_all(db: Session, feeds: list[dict], feed_rows: dict[str, Feed] | None = None) -> list[dict]:
    """Ingest a list of {'name', 'url'} feeds. Returns stats per feed."""
    feed_rows = feed_rows or {}
    return [
        ingest_feed(db, f["url"], f["name"], feed=feed_rows.get(f["name"]))
        for f in feeds
    ]


def utcnow():
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)
