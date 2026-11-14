"""Source reliability analysis: an explainable, evidence-based profile of each outlet.

This is **not an editorial rating** and does not judge whether an outlet is "true". It summarises
signals SignalDesk can actually observe about how an outlet publishes, over the last
:data:`WINDOW_DAYS` days of the shared data, and shows its working so a reader can disagree with it:

    Transparency   30  author named, publication dated, sources linked, a corrections/standards link
    Corrections    10  a corrections practice exists; a high rate of correction notices counts against it
    Information    20  the mean information score of its reports (see :mod:`app.quality`)
    Corroboration  20  how often other outlets cover the same events (50% of reports is a full mark)
    Agreement      10  of the claims it makes in compared stories, the share that are not disputed
    Availability   10  how often its feed answered (see :mod:`app.observability`)

A component without enough evidence is left out and the score is rescaled over what is known; with too
little evidence overall the score is simply withheld ("not enough data"). Visitor workspaces never
contribute: every query is restricted to the shared data.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Article, EventArticle, FeedRun, StoryBrief
from .story_index import _as_utc

WINDOW_DAYS = 30
MIN_ARTICLES = 10      # reports needed before a profile is shown at all
MIN_SIGNALS = 5        # pages with readable signals needed for transparency and corrections
MIN_CLAIMS = 5         # compared claims needed for the agreement component
MIN_FEED_RUNS = 10     # feed checks needed for availability
MIN_KNOWN_WEIGHT = 40  # of 100: below this much evidence the score is withheld
CACHE_SECONDS = 600
NOTE = ("Derived from signals SignalDesk observed in its own data over the last 30 days. It describes how an "
        "outlet publishes, not whether it is right, and is not an editorial rating.")

WEIGHTS = {"transparency": 30, "corrections": 10, "information": 20, "corroboration": 20,
           "agreement": 10, "availability": 10}
LABELS = {"transparency": "Transparency", "corrections": "Corrections", "information": "Information",
          "corroboration": "Corroboration", "agreement": "Agreement", "availability": "Availability"}

_cache: dict[str, Any] = {"at": 0.0, "value": None}
_lock = threading.Lock()


def reset_cache() -> None:
    """Forget the cached profiles (tests, and anything that changes the underlying data in place)."""
    with _lock:
        _cache.update(at=0.0, value=None)


def label_for(score: int | None) -> str:
    """Words for a score band. Deliberately about signals, not trustworthiness."""
    if score is None:
        return "Not enough data"
    return "Strong signals" if score >= 75 else "Mixed signals" if score >= 55 else "Weak signals"


def _pct(value: float) -> str:
    """A fraction as a whole percentage."""
    return f"{round(value * 100)}%"


def _transparency(sig: list[dict]) -> tuple[float | None, str]:
    """Points and an explanation from the pages' signals."""
    if len(sig) < MIN_SIGNALS:
        return None, f"Only {len(sig)} readable pages so far"
    n = len(sig)
    byline = sum(bool(s.get("byline")) for s in sig) / n
    dated = sum(bool(s.get("published")) for s in sig) / n
    sourced = sum(s.get("sources", 0) > 0 for s in sig) / n
    policy = sum(bool(s.get("policy")) for s in sig) / n
    points = WEIGHTS["transparency"] * (0.35 * byline + 0.25 * dated + 0.25 * sourced + 0.15 * policy)
    return points, (f"Across {n} pages: author named on {_pct(byline)}, dated on {_pct(dated)}, "
                    f"links its sources on {_pct(sourced)}, standards or corrections link on {_pct(policy)}")


def _corrections(sig: list[dict]) -> tuple[float | None, str, dict]:
    """Points, explanation and raw figures for the corrections practice."""
    n = len(sig)
    notices = sum(bool(s.get("correction")) for s in sig)
    policy = n and sum(bool(s.get("policy")) for s in sig) / n > 0.5
    figures = {"notices": notices, "rate": round(notices / n, 3) if n else 0.0, "policy": bool(policy)}
    if n < MIN_SIGNALS:
        return None, f"Only {n} readable pages so far", figures
    practice = policy or notices > 0
    points = max(0, min(WEIGHTS["corrections"], (WEIGHTS["corrections"] if practice else 0) - min(5, round(figures["rate"] * 50))))
    detail = ("Shows a corrections practice" if practice else "No corrections practice found") + \
             f"; {notices} correction notice{'s' if notices != 1 else ''} in {n} pages ({_pct(figures['rate'])})"
    return points, detail, figures


def compute(db: Session, now: datetime | None = None) -> dict[str, dict]:
    """Profiles of every outlet with shared reports in the window, keyed by source name."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=WINDOW_DAYS)
    rows = db.execute(
        select(Article.id, Article.source, Article.info_score, Article.signals, Article.published_at, Article.ingested_at,
               EventArticle.event_id)
        .outerjoin(EventArticle, EventArticle.article_id == Article.id)
        .where(Article.is_seed.is_(False), Article.workspace_id == "", Article.ingested_at >= since)
    ).all()
    by_source: dict[str, list] = defaultdict(list)
    event_sources: dict[int, set[str]] = defaultdict(set)
    event_first: dict[int, tuple[datetime, str]] = {}
    for r in rows:
        by_source[r.source].append(r)
        if r.event_id is not None:
            event_sources[r.event_id].add(r.source)
            when = _as_utc(r.published_at or r.ingested_at)
            if r.event_id not in event_first or when < event_first[r.event_id][0]:
                event_first[r.event_id] = (when, r.source)
    multi = {e for e, sources in event_sources.items() if len(sources) >= 2}

    feed_runs: dict[str, list[bool]] = defaultdict(list)
    for feed, ok in db.execute(select(FeedRun.feed, FeedRun.ok).where(FeedRun.at >= since)).all():
        feed_runs[feed].append(ok)

    agree: dict[str, int] = defaultdict(int)
    dispute: dict[str, int] = defaultdict(int)
    cached = db.execute(select(StoryBrief.claims).join(Article, Article.id == StoryBrief.cluster_id)
                        .where(StoryBrief.claims.is_not(None), Article.workspace_id == "")).scalars().all()
    for blob in cached:
        try:
            items = json.loads(blob).get("items", [])
        except (json.JSONDecodeError, AttributeError):
            continue
        for item in items:
            bucket = agree if item.get("status") == "agreed" else dispute if item.get("status") == "disputed" else None
            for outlet in item.get("outlets", []) if bucket is not None else []:
                bucket[outlet] += 1

    profiles = {}
    for source, items in by_source.items():
        sig = []
        for r in items:
            try:
                parsed = json.loads(r.signals) if r.signals else None
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                sig.append(parsed)
        n = len(items)
        scores = [r.info_score for r in items if r.info_score is not None]
        corroborated = sum(1 for r in items if r.event_id in multi) / n
        led = [e for e in multi if source in event_sources[e]]
        first_rate = sum(1 for e in led if event_first[e][1] == source) / len(led) if led else None
        runs = feed_runs.get(source, [])
        claims_seen = agree[source] + dispute[source]

        t_points, t_detail = _transparency(sig)
        c_points, c_detail, corr = _corrections(sig)
        parts: dict[str, tuple[float | None, str]] = {
            "transparency": (t_points, t_detail),
            "corrections": (c_points, c_detail),
            "information": ((WEIGHTS["information"] * (sum(scores) / len(scores)) / 100, f"Mean information score {round(sum(scores) / len(scores))}/100 over {len(scores)} reports")
                            if len(scores) >= MIN_ARTICLES else (None, f"Only {len(scores)} scored reports so far")),
            "corroboration": ((WEIGHTS["corroboration"] * min(1.0, corroborated / 0.5), f"{_pct(corroborated)} of its reports are on events other outlets also cover")
                              if n >= MIN_ARTICLES else (None, f"Only {n} reports so far")),
            "agreement": ((WEIGHTS["agreement"] * agree[source] / claims_seen, f"{agree[source]} of {claims_seen} compared claims agreed with other outlets")
                          if claims_seen >= MIN_CLAIMS else (None, f"Only {claims_seen} compared claims so far")),
            "availability": ((WEIGHTS["availability"] * sum(runs) / len(runs), f"Feed answered on {_pct(sum(runs) / len(runs))} of {len(runs)} checks")
                             if len(runs) >= MIN_FEED_RUNS else (None, f"Only {len(runs)} feed checks so far")),
        }
        known = sum(WEIGHTS[k] for k, (p, _) in parts.items() if p is not None)
        score = None
        if n >= MIN_ARTICLES and known >= MIN_KNOWN_WEIGHT:
            score = round(100 * sum(p for p, _ in parts.values() if p is not None) / known)
        profiles[source] = {
            "source": source, "articles": n, "score": score, "label": label_for(score),
            "breakdown": [{"key": k, "label": LABELS[k], "points": None if p is None else round(p, 1),
                           "max": WEIGHTS[k], "detail": detail} for k, (p, detail) in parts.items()],
            "corroboration_rate": round(corroborated, 3),
            "first_report_rate": None if first_rate is None else round(first_rate, 3),
            "corrections": corr,
        }
    return profiles


def profiles(db: Session) -> dict[str, dict]:
    """Cached profiles (rebuilt every CACHE_SECONDS; the data changes slowly and the query is not free)."""
    with _lock:
        if _cache["value"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
            return _cache["value"]
    value = compute(db)
    with _lock:
        _cache.update(at=time.time(), value=value)
    return value


def listing(db: Session) -> dict:
    """The sources view: every profile, best first, with the standing disclaimer."""
    items = sorted(profiles(db).values(), key=lambda p: (p["score"] is None, -(p["score"] or 0), p["source"].lower()))
    return {"note": NOTE, "window_days": WINDOW_DAYS, "items": items}
