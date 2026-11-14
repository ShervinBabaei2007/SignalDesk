"""The ingest cycle: fetch feeds, raise watch alerts, then enrich what is waiting.

One module owns the whole cycle so the manual "Ingest feeds" button and the
auto-pilot scheduler follow the same rules:

* one cycle at a time (``Busy`` when another is running),
* a cooldown after every run, enforced for manual runs so rapid clicking cannot
  hammer every RSS origin (the scheduler waits for a free slot but not the cooldown),
* only active feeds are fetched,
* a watchlist problem never fails an ingest,
* the definition of "waiting for enrichment" lives in :mod:`app.enrichment`.

Callers: ``POST /api/ingest`` runs :func:`ingest_cycle` and queues
:func:`enrich_backlog` in the background; the scheduler runs :func:`scheduled_cycle`.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config, enrichment, watches
from .database import SessionLocal
from .ingestion import ingest_all
from .models import Article, Feed

logger = logging.getLogger("signaldesk.pipeline")

_lock = threading.Lock()  # prevents overlapping cycles
_last_finished = 0.0
MAX_ENRICH_WAVES = 12


class Busy(Exception):
    """A cycle is running, or one finished inside the cooldown window."""


@dataclass
class CycleResult:
    """Outcome of one ingest cycle: per-feed results, new alerts and what is still waiting for enrichment."""
    results: list[dict]
    duration_seconds: float
    alerts: list[dict] = field(default_factory=list)
    enrich_pending: int = 0         # articles still waiting for a full-text summary
    enrich_needed: bool = False     # pending summaries or missing lead images to fill in


def ingest_cycle(db: Session, *, manual: bool,
                 ingest: Callable[..., list[dict]] | None = None) -> CycleResult:
    """Fetch every active feed and check the watchlist. Raises :class:`Busy` if not allowed now.

    `manual` is the button; those runs respect and start the cooldown, scheduled runs do neither
    (they only wait for a free slot). `ingest` is the fetch seam (defaults to
    :func:`app.ingestion.ingest_all`); tests pass a fake so nothing touches the network.
    """
    global _last_finished
    busy = Busy("An ingestion just ran — give the feeds a moment before refreshing again.")
    if manual and time.time() - _last_finished < config.INGEST_COOLDOWN_SECONDS:
        raise busy
    if not _lock.acquire(blocking=False):
        raise busy
    try:
        feed_rows = {f.name: f for f in db.execute(select(Feed).where(Feed.is_active)).scalars().all()}
        feeds = [{"name": f.name, "url": f.url} for f in feed_rows.values()]
        started = time.perf_counter()
        results = (ingest or ingest_all)(db, feeds, feed_rows=feed_rows)
        duration = time.perf_counter() - started
        if manual:
            _last_finished = time.time()
    finally:
        _lock.release()

    pending = db.scalar(select(func.count()).select_from(Article).where(*enrichment.pending_clauses())) or 0
    missing_images = db.scalar(
        select(func.count()).select_from(Article).where(*enrichment.missing_image_clauses())) or 0

    try:
        alerts = watches.check_watches(db)
    except Exception:  # noqa: BLE001 - a watchlist problem must never fail an ingest
        logger.exception("[watch] check failed")
        alerts = []

    return CycleResult(results=results, duration_seconds=round(duration, 2), alerts=alerts,
                       enrich_pending=pending, enrich_needed=bool(pending or missing_images))


def enrich_backlog(session_factory: Callable[[], Session] | None = None,
                   enrich: Callable[[Session], dict] | None = None) -> None:
    """Enrich pending articles wave by wave, so a big ingest is fully enriched,
    stopping if a wave makes no progress."""
    with (session_factory or SessionLocal)() as db:
        try:
            for _ in range(MAX_ENRICH_WAVES):
                stats = (enrich or enrichment.enrich_pending_articles)(db)
                logger.info("[enrich] deep summaries generated for %s articles (%s remaining)",
                            stats["enriched"], stats["remaining"])
                if not stats["enriched"] or not stats["remaining"]:
                    break
        except Exception:  # noqa: BLE001
            logger.exception("[enrich] enrichment failed")


def scheduled_cycle(session_factory: Callable[[], Session] | None = None,
                    ingest: Callable[..., list[dict]] | None = None,
                    enrich: Callable[[Session], dict] | None = None) -> CycleResult | None:
    """One auto-pilot round, run in a worker thread: ingest, check the watchlist, enrich the backlog.

    Returns None when a manual ingest is already running (the next round will catch up).
    """
    with (session_factory or SessionLocal)() as db:
        try:
            result = ingest_cycle(db, manual=False, ingest=ingest)
        except Busy:
            logger.info("[scheduler] skipped: an ingestion is already running")
            return None
        logger.info("[scheduler] auto-ingest finished: +%s new articles",
                    sum(r["added"] for r in result.results))
    # Without this, scheduled articles would keep low information scores
    # until someone pressed "Ingest feeds".
    enrich_backlog(session_factory, enrich)
    return result
