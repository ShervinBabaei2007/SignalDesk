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

from . import story_index
from .models import Article, FeedRun, StoryBrief
from .story_index import _as_utc

WINDOW_DAYS = 30       # days of shared data a profile is built from
MIN_ARTICLES = 10      # reports needed before a profile is shown at all
MIN_SIGNALS = 5        # pages with readable signals needed for transparency and corrections
MIN_CLAIMS = 5         # compared claims needed for the agreement component
MIN_FEED_RUNS = 10     # feed checks needed for availability
MIN_KNOWN_WEIGHT = 60  # of 100: below this much evidence the score is withheld (in practice: page signals are needed)
MIN_WINDOW = 6         # recent reports needed before corroboration is judged
CACHE_SECONDS = 600    # how long computed profiles are reused (10 minutes)
NOTE = ("Derived from signals SignalDesk observed in its own data over the last 30 days. It describes how an "
        "outlet publishes, not whether it is right, and is not an editorial rating.")

STRONG, MIXED = 70, 45  # score bands; the frontend mirrors these in lib/insights.ts
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
    if score >= STRONG:
        return "Strong signals"
    if score >= MIXED:
        return "Mixed signals"
    return "Limited signals"


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
    # Sub-weights sum to 1: a named author matters most, a standards link least.
    points = WEIGHTS["transparency"] * (0.35 * byline + 0.25 * dated + 0.25 * sourced + 0.15 * policy)
    return points, (f"Across {n} pages: author named on {_pct(byline)}, dated on {_pct(dated)}, "
                    f"links its sources on {_pct(sourced)}, standards or corrections link on {_pct(policy)}")


def _corrections(sig: list[dict]) -> tuple[float | None, str, dict]:
    """Points, explanation and raw figures for the corrections practice."""
    n = len(sig)
    notices = sum(bool(s.get("correction")) for s in sig)
    policy = n and sum(bool(s.get("policy")) for s in sig) / n > 0.5  # a standards link on most pages counts as a policy
    figures = {"notices": notices, "rate": round(notices / n, 3) if n else 0.0, "policy": bool(policy)}
    if n < MIN_SIGNALS:
        return None, f"Only {n} readable pages so far", figures
    practice = policy or notices > 0
    # Full marks for a visible practice, minus up to 5 points as the notice rate climbs (10% of pages costs all 5).
    points = max(0, min(WEIGHTS["corrections"], (WEIGHTS["corrections"] if practice else 0) - min(5, round(figures["rate"] * 50))))
    detail = ("Shows a corrections practice" if practice else "No corrections practice found") + \
             f"; {notices} correction notice{'s' if notices != 1 else ''} in {n} pages ({_pct(figures['rate'])})"
    return points, detail, figures


def compute(db: Session, now: datetime | None = None) -> dict[str, dict]:
    """Profiles of every outlet with shared reports in the window, keyed by source name."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=WINDOW_DAYS)
    rows = db.execute(
        select(Article.id, Article.source, Article.info_score, Article.signals, Article.published_at, Article.ingested_at)
        .where(Article.is_seed.is_(False), Article.workspace_id == "", Article.ingested_at >= since)
    ).all()
    by_source: dict[str, list] = defaultdict(list)
    # Group the window's reports by outlet.
    for r in rows:
        by_source[r.source].append(r)

    # Corroboration comes from the live story clusters of the shared data (the last few days), so it is
    # judged on the same articles and the same grouping the app shows; older reports are not assessed.
    previous = db.info.get("workspace", "")
    db.info["workspace"] = ""
    try:
        by_article, _, window_ids = story_index._load(db)
    finally:
        db.info["workspace"] = previous
    in_window = set(window_ids)
    multi = {c.id: c for c in set(by_article.values()) if len(c.sources) >= 2}  # stories with two or more outlets
    stamp = {r.id: _as_utc(r.published_at or r.ingested_at) for r in rows}
    source_of = {r.id: r.source for r in rows}
    # The outlet behind each multi-outlet story's earliest report (ties broken by article id).
    first_source ={cid: source_of.get(min(c.article_ids, key=lambda i: (stamp.get(i) or now, i))) for cid, c in multi.items()}

    feed_runs: dict[str, list[bool]] = defaultdict(list)
    # Each feed's success history over the window (feeds are named after their outlet).
    for feed, ok in db.execute(select(FeedRun.feed, FeedRun.ok).where(FeedRun.at >= since)).all():
        feed_runs[feed].append(ok)

    agree: dict[str, int] = defaultdict(int)
    dispute: dict[str, int] = defaultdict(int)
    cached = db.execute(select(StoryBrief.claims).join(Article, Article.id == StoryBrief.cluster_id)
                        .where(StoryBrief.claims.is_not(None), Article.workspace_id == "")).scalars().all()
    # Tally, per outlet, the agreed and disputed claims from every cached claim comparison.
    for blob in cached:
        try:
            items = json.loads(blob).get("items", [])
        except (json.JSONDecodeError, AttributeError):
            continue  # skip unreadable cache entries
        for item in items:
            status = item.get("status")
            if status == "agreed":
                bucket = agree
            elif status == "disputed":
                bucket = dispute
            else:
                continue  # single-outlet claims say nothing about agreement
            for outlet in item.get("outlets", []):
                bucket[outlet] += 1

    profiles = {}
    # Build one profile per outlet from its reports and the shared tallies above.
    for source, items in by_source.items():
        sig = []
        # Collect the readable page signals, ignoring missing or malformed JSON.
        for r in items:
            try:
                parsed = json.loads(r.signals) if r.signals else None
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                sig.append(parsed)
        n = len(items)
        scores = [r.info_score for r in items if r.info_score is not None]
        recent = [r for r in items if r.id in in_window]
        corroborated = sum(1 for r in recent if by_article.get(r.id) and by_article[r.id].id in multi) / len(recent) if recent else 0.0
        led = [cid for cid, c in multi.items() if source in c.sources]
        first_rate = sum(1 for cid in led if first_source.get(cid) == source) / len(led) if led else None
        runs = feed_runs.get(source, [])
        claims_seen = agree[source] + dispute[source]

        t_points, t_detail = _transparency(sig)
        c_points, c_detail, corr = _corrections(sig)
        # Each component is (points, explanation), or (None, why) when there is not enough evidence yet.
        # Corroboration earns full marks once half of the outlet's recent reports are corroborated.
        parts: dict[str, tuple[float | None, str]] = {
            "transparency": (t_points, t_detail),
            "corrections": (c_points, c_detail),
            "information": ((WEIGHTS["information"] * (sum(scores) / len(scores)) / 100, f"Mean information score {round(sum(scores) / len(scores))}/100 over {len(scores)} reports")
                            if len(scores) >= MIN_ARTICLES else (None, f"Only {len(scores)} scored reports so far")),
            "corroboration": ((WEIGHTS["corroboration"] * min(1.0, corroborated / 0.5), f"{_pct(corroborated)} of its last {len(recent)} recent reports are on events other outlets also cover")
                              if len(recent) >= MIN_WINDOW else (None, f"Only {len(recent)} recent reports to compare so far")),
            "agreement": ((WEIGHTS["agreement"] * agree[source] / claims_seen, f"{agree[source]} of {claims_seen} compared claims agreed with other outlets")
                          if claims_seen >= MIN_CLAIMS else (None, f"Only {claims_seen} compared claims so far")),
            "availability": ((WEIGHTS["availability"] * sum(runs) / len(runs), f"Feed answered on {_pct(sum(runs) / len(runs))} of {len(runs)} checks")
                             if len(runs) >= MIN_FEED_RUNS else (None, f"Only {len(runs)} feed checks so far")),
        }
        known = sum(WEIGHTS[k] for k, (p, _) in parts.items() if p is not None)
        score = None
        # Rescale the known components to 100, but only with enough reports and enough known weight.
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
        # Serve the cached profiles while they are younger than CACHE_SECONDS.
        if _cache["value"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
            return _cache["value"]
    value = compute(db)
    with _lock:
        _cache.update(at=time.time(), value=value)
    return value


def listing(db: Session) -> dict:
    """The sources view: every profile, best first, with the standing disclaimer."""
    # Scored outlets first, highest score first, then alphabetically.
    items = sorted(profiles(db).values(), key=lambda p: (p["score"] is None, -(p["score"] or 0), p["source"].lower()))
    return {"note": NOTE, "window_days": WINDOW_DAYS, "items": items}
