"""RSS ingestion pipeline: fetch feeds, dedupe, analyze, store."""

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import mktime

import feedparser
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .analysis import analyze
from .models import Article, Feed

logger = logging.getLogger("signaldesk.ingestion")

DEFAULT_FEEDS = [
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "BBC Technology", "url": "https://feeds.bbci.co.uk/news/technology/rss.xml"},
    {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
    {"name": "Hacker News", "url": "https://hnrss.org/frontpage"},
]


def _parse_published(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        value = getattr(entry, attr, None)
        if value:
            try:
                return datetime.fromtimestamp(mktime(value), tz=timezone.utc)
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


def _entry_text(entry) -> str:
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
    return f"{title}. {body}".strip()


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
        if feed is not None:
            feed.last_fetched_at = datetime.now(timezone.utc)
            feed.last_status = status[:300]
            db.commit()

    try:
        parsed = feedparser.parse(feed_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Feed %s failed to parse: %s", feed_url, exc)
        stats["error"] = str(exc)
        _finish(f"error: {exc}")
        return stats

    entries = (parsed.entries or [])[:max_entries]
    stats["fetched"] = len(entries)

    for entry in entries:
        url = getattr(entry, "link", None)
        title = (getattr(entry, "title", None) or "").strip()
        if not url or not title:
            stats["skipped"] += 1
            continue

        exists = db.scalar(select(Article.id).where(Article.url == url))
        if exists:
            stats["skipped"] += 1
            continue

        text = _entry_text(entry)
        result = analyze(text)
        article = Article(
            title=title[:500],
            url=url[:1000],
            source=feed_name[:200],
            summary=result["summary"],
            keywords=", ".join(result["keywords"]),
            topic=result["topic"],
            sentiment=result["sentiment"],
            published_at=_parse_published(entry),
        )
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
    return datetime.now(timezone.utc)
