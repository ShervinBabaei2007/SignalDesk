"""Article enrichment: fetch the original page, extract readable text, and
generate a clean, straightforward summary that's easier to read than the
often-gibberish RSS titles/excerpts.

Runs in the background after ingestion so the ingest endpoint stays fast.
If a page can't be fetched (paywall, JS-only site, offline), we fall back to
a summary built from the stored feed text — the user always gets a summary.
"""

import threading
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .analysis import extract_keywords, structured_summary, summarize
from .extractor import extract_main_text
from .ingestion import strip_feed_metadata
from .models import Article

# Serialize enrichment: SQLite dislikes concurrent writers
_lock = threading.Lock()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 SignalDesk/2.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_full_text(url: str, timeout: float = 12.0) -> str | None:
    """Download a page and return its extracted readable text, or None."""
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=timeout, follow_redirects=True)
    except Exception:  # noqa: BLE001  (network errors are expected sometimes)
        return None
    if resp.status_code != 200:
        return None
    content_type = resp.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        return None
    try:
        text = extract_main_text(resp.text)
    except Exception:  # noqa: BLE001
        return None
    # Require a meaningful amount of text to call it a success
    return text if len(text) > 200 else None


def enrich_article(db: Session, article: Article) -> bool:
    """Populate full_text + summary_deep for one article. Always succeeds:
    uses stored feed text as fallback when the page isn't fetchable."""
    if article.enriched_at is not None:
        return False

    fetched = None
    if not article.is_seed:
        fetched = fetch_full_text(article.url)

    if fetched or article.full_text:
        if fetched:
            article.full_text = fetched
        article.summary_deep = summarize(article.full_text, max_sentences=4,
                                         max_chars=500, avoid=article.title)
        article.summary_structured = structured_summary(article.full_text, article.title)
        new_keywords = extract_keywords(article.full_text)
        if new_keywords:
            article.keywords = ", ".join(new_keywords)
    else:
        # Fallback: summarize the stored feed text (never repeat the headline —
        # the title is already displayed above the summary in the UI).
        source_text = strip_feed_metadata(article.summary or article.title)
        article.summary_deep = summarize(source_text, max_sentences=3, max_chars=400)
        article.summary_structured = structured_summary(source_text, article.title)

    article.enriched_at = datetime.now(timezone.utc)
    db.commit()
    return True


def enrich_pending_articles(db: Session, limit: int = 30) -> dict:
    """Enrich up to `limit` articles that don't have a deep summary yet."""
    with _lock:
        pending = db.execute(
            select(Article)
            .where(Article.enriched_at.is_(None), Article.is_seed.is_(False))
            .order_by(Article.published_at.desc().nullslast())
            .limit(limit)
        ).scalars().all()

        enriched = 0
        for article in pending:
            if enrich_article(db, article):
                enriched += 1

        remaining = db.scalar(
            select(func.count()).select_from(Article).where(
                Article.enriched_at.is_(None), Article.is_seed.is_(False))
        ) or 0
        return {"enriched": enriched, "remaining": remaining}
