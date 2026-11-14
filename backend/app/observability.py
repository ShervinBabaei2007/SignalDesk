"""Pipeline observability: record every ingest cycle and summarise how healthy the pipeline is.

Each cycle of the *shared* data writes one :class:`PipelineRun` and one :class:`FeedRun` per feed
(visitor workspaces are never recorded, so the numbers describe the product, not demo traffic).
:func:`summary` turns those rows, plus the articles' own ``extraction`` status, into the figures an
operator needs: did the cycles run, how long did they take, which feeds fail, how much came in per
hour, and how often the full article page could actually be read.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import embeddings, enrichment
from .models import Article, FeedRun, PipelineRun

logger = logging.getLogger("signaldesk.observability")

RETENTION_DAYS = 30  # run history older than this is purged by the cron


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile of `values` (0 for an empty list)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    # Nearest rank is ceil(pct% of n), 1-based; clamp to the first element for pct 0.
    return float(ordered[max(math.ceil(pct / 100 * len(ordered)) - 1, 0)])


def record_cycle(db: Session, *, kind: str, duration_seconds: float, results: list[dict], alerts: int = 0,
                 error: str | None = None) -> int | None:
    """Store one cycle and its per-feed rows. Never raises: observability must not break an ingest."""
    if db.info.get("workspace"):
        return None
    try:
        failed = [r for r in results if r.get("error")]
        run = PipelineRun(
            kind=kind, duration_ms=round(duration_seconds * 1000), ok=error is None, error=(error or None) and error[:300],
            feeds_ok=len(results) - len(failed), feeds_failed=len(failed),
            fetched=sum(r.get("fetched", 0) for r in results), added=sum(r.get("added", 0) for r in results),
            skipped=sum(r.get("skipped", 0) for r in results), alerts=alerts,
        )
        db.add(run)
        db.flush()  # assigns run.id for the per-feed rows
        # One FeedRun per feed result, with text truncated to the column sizes.
        for r in results:
            db.add(FeedRun(run_id=run.id, feed=str(r.get("feed", "?"))[:200], ok=not r.get("error"),
                           error=(str(r["error"])[:300] if r.get("error") else None),
                           latency_ms=int(r.get("latency_ms", 0)), fetched=r.get("fetched", 0), added=r.get("added", 0)))
        db.commit()
        logger.info("[pipeline] kind=%s duration_ms=%s feeds_ok=%s feeds_failed=%s fetched=%s added=%s alerts=%s",
                    kind, run.duration_ms, run.feeds_ok, run.feeds_failed, run.fetched, run.added, alerts)
        return run.id
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("[pipeline] could not record the cycle")
        return None


def purge_old(db: Session, now: datetime | None = None) -> int:
    """Delete run history older than RETENTION_DAYS (called from the cron). Returns rows removed."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=RETENTION_DAYS)
    removed = db.execute(delete(FeedRun).where(FeedRun.at < cutoff)).rowcount or 0
    removed += db.execute(delete(PipelineRun).where(PipelineRun.started_at < cutoff)).rowcount or 0
    db.commit()
    return removed


def _aware(dt: datetime) -> datetime:
    """Treat a naive datetime (SQLite) as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _unembedded(db: Session, now: datetime) -> int:
    """Recent shared articles still waiting for an embedding."""
    cutoff = now - timedelta(days=embeddings.WINDOW_DAYS)
    return db.scalar(select(func.count()).select_from(Article).where(
        Article.is_seed.is_(False), Article.workspace_id == "", Article.embedding.is_(None),
        (Article.published_at >= cutoff) | Article.published_at.is_(None))) or 0


def summary(db: Session, hours: int = 24, now: datetime | None = None) -> dict:
    """Health figures for the last `hours` hours of the shared pipeline."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    runs = list(db.execute(select(PipelineRun).where(PipelineRun.started_at >= since)
                           .order_by(PipelineRun.started_at)).scalars())
    feed_rows = list(db.execute(select(FeedRun).where(FeedRun.at >= since).order_by(FeedRun.at)).scalars())

    durations = [r.duration_ms for r in runs]
    last = max(runs, key=lambda r: r.started_at, default=None)
    last_ok = max((r for r in runs if r.ok), key=lambda r: r.started_at, default=None)

    by_feed: dict[str, list[FeedRun]] = defaultdict(list)
    # Group the window's feed checks by feed, oldest first.
    for row in feed_rows:
        by_feed[row.feed].append(row)
    feeds = []
    # Summarise each feed's reliability, latency and yield.
    for name, rows in by_feed.items():
        failures = [r for r in rows if not r.ok]
        feeds.append({
            "feed": name, "runs": len(rows), "failures": len(failures),
            "failure_rate": round(len(failures) / len(rows), 3),
            "p95_latency_ms": round(percentile([r.latency_ms for r in rows], 95)),
            "articles_added": sum(r.added for r in rows),
            "last_error": failures[-1].error if failures else None,
            "last_ok_at": max((r.at for r in rows if r.ok), default=None),
        })
    feeds.sort(key=lambda f: (-f["failure_rate"], -f["runs"], f["feed"]))  # worst feeds first

    # throughput: new articles per hour for a day or less, per day beyond that
    step = "%Y-%m-%dT%H:00" if hours <= 48 else "%Y-%m-%d"
    series: dict[str, int] = defaultdict(int)
    # Sum each run's new articles into its hour (or day) bucket.
    for r in runs:
        series[_aware(r.started_at).strftime(step)] += r.added
    added = sum(r.added for r in runs)

    # Articles enriched in the window whose full page was read, versus those that fell back to feed text.
    page, fallback = (db.scalar(select(func.count()).select_from(Article)
                                .where(Article.is_seed.is_(False), Article.enriched_at >= since,
                                       Article.extraction == kind)) or 0 for kind in ("page", "fallback"))
    backlog = db.scalar(select(func.count()).select_from(Article).where(*enrichment.pending_clauses())) or 0

    return {
        "window_hours": hours,
        "runs": {
            "total": len(runs), "failed": sum(1 for r in runs if not r.ok),
            "success_rate": round(sum(1 for r in runs if r.ok) / len(runs), 3) if runs else None,
            "p50_ms": round(percentile(durations, 50)), "p95_ms": round(percentile(durations, 95)),
            "last_at": last.started_at if last else None,
            "last_ok_at": last_ok.started_at if last_ok else None,
            "minutes_since_ok": round((now - _aware(last_ok.started_at)).total_seconds() / 60) if last_ok else None,
        },
        "throughput": {
            "added": added, "per_hour": round(added / hours, 2),
            "series": [{"at": k, "added": v} for k, v in sorted(series.items())],
        },
        "feeds": {"ok": sum(1 for f in feeds if not f["failures"]), "failing": sum(1 for f in feeds if f["failures"]),
                  "items": feeds},
        "extraction": {"page": page, "fallback": fallback,
                       "success_rate": round(page / (page + fallback), 3) if page + fallback else None},
        "backlog": {"awaiting_enrichment": backlog,
                    "awaiting_embedding": _unembedded(db, now) if embeddings.available() else None},
    }
