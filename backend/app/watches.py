"""Watchlists: get told when a story you care about breaks.

A watch is a term (a word or phrase), an optional topic, and a minimum number of
outlets. After every ingest, each active watch is checked against the recent
stories (see :mod:`app.clustering`). A story that matches and is covered by
enough outlets raises one alert, ever: `watch_alerts` remembers (watch, story)
pairs so the same story never alerts twice.

Alerts always show up in the dashboard after an ingest; if Slack or email is
configured (see :mod:`app.notifications`) they are delivered there as well.
Creating a watch records today's matching stories as already seen, so a new
watch only reports stories that appear *after* it was created.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clustering, notifications
from .models import Article, Watch, WatchAlert

logger = logging.getLogger("signaldesk.watches")

MAX_WATCHES = 25


def term_matches(term: str, text: str) -> bool:
    """Whole-word / whole-phrase, case-insensitive ('AI' does not match 'said')."""
    return bool(re.search(rf"(?<!\w){re.escape(term.strip())}(?!\w)", text, re.IGNORECASE))


def story_text(members: list[Article]) -> str:
    return " ".join(f"{m.title} {m.summary or ''}" for m in members)


def matches(watch: Watch, members: list[Article]) -> bool:
    if watch.topic and not any(m.topic == watch.topic for m in members):
        return False
    return term_matches(watch.term, story_text(members))


def matching_terms(watches: list[Watch], members: list[Article]) -> list[str]:
    """Terms of the active watches that this story matches (for the feed badge)."""
    return [w.term for w in watches if w.is_active and matches(w, members)]


def active(db: Session) -> list[Watch]:
    return list(db.execute(select(Watch).where(Watch.is_active.is_(True)).order_by(Watch.id)).scalars())


def recent_stories(db: Session) -> list[tuple[str, list[Article]]]:
    """[(story key, member articles)] for the recent window; keys match the feed's story keys."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=clustering.WINDOW_DAYS)
    rows = db.execute(
        select(Article)
        .where(Article.is_seed.is_(False), (Article.published_at >= cutoff) | Article.published_at.is_(None))
        .order_by(Article.id.desc())
        .limit(clustering.MAX_ARTICLES)
    ).scalars().all()
    by_article, _ = clustering.get_clusters(db)
    groups: dict[str, list[Article]] = {}
    for a in rows:
        cluster = by_article.get(a.id)
        groups.setdefault(f"c{cluster.id}" if cluster else f"a{a.id}", []).append(a)
    return list(groups.items())


def _headline(key: str, members: list[Article], by_id: dict) -> tuple[str, int | None, int]:
    """(title, cluster id, lead article id) for an alert."""
    if key.startswith("c"):
        cluster = by_id.get(int(key[1:]))
        if cluster is not None:
            return cluster.title, cluster.id, cluster.lead_id
    return members[0].title, None, members[0].id


def matching_stories(db: Session, watch: Watch) -> list[tuple[str, list[Article]]]:
    return [
        (key, members) for key, members in recent_stories(db)
        if len({m.source for m in members}) >= watch.min_outlets and matches(watch, members)
    ]


def baseline(db: Session, watch: Watch) -> int:
    """Mark the stories that already match as seen, so only new ones alert."""
    keys = {k for (k,) in db.execute(select(WatchAlert.story_key).where(WatchAlert.watch_id == watch.id))}
    added = 0
    for key, _ in matching_stories(db, watch):
        if key not in keys:
            db.add(WatchAlert(watch_id=watch.id, story_key=key, notified=False))
            added += 1
    if added:
        db.commit()
    return added


def check_watches(db: Session, deliver: bool = True) -> list[dict]:
    """Raise one alert per (watch, story) that newly matches. Returns the new alerts."""
    watches = active(db)
    if not watches:
        return []
    _, by_id = clustering.get_clusters(db)
    stories = recent_stories(db)
    alerts: list[dict] = []
    for watch in watches:
        seen = {k for (k,) in db.execute(select(WatchAlert.story_key).where(WatchAlert.watch_id == watch.id))}
        for key, members in stories:
            if key in seen:
                continue
            outlets = len({m.source for m in members})
            if outlets < watch.min_outlets or not matches(watch, members):
                continue
            title, cluster_id, article_id = _headline(key, members, by_id)
            db.add(WatchAlert(watch_id=watch.id, story_key=key, notified=False))
            alerts.append({
                "watch_id": watch.id, "term": watch.term, "story_key": key, "cluster_id": cluster_id,
                "article_id": article_id, "title": title, "outlets": outlets, "reports": len(members),
            })
    if alerts:
        db.commit()
        if deliver and notifications.configured_channels():
            result = notifications.deliver_alert(alert_subject(alerts), alert_text(alerts))
            if result["sent"]:
                for row in db.execute(
                    select(WatchAlert).where(WatchAlert.notified.is_(False),
                                             WatchAlert.story_key.in_([a["story_key"] for a in alerts]))
                ).scalars():
                    row.notified = True
                db.commit()
        logger.info("[watch] %s new alert(s)", len(alerts))
    return alerts


def alert_subject(alerts: list[dict]) -> str:
    first = alerts[0]
    more = f" (+{len(alerts) - 1} more)" if len(alerts) > 1 else ""
    return f"SignalDesk alert: \"{first['term']}\" — {first['title'][:80]}{more}"


def alert_text(alerts: list[dict]) -> str:
    lines = ["Stories matching your watchlist:", ""]
    for a in alerts:
        lines.append(f"• [{a['term']}] {a['title']} — {a['reports']} reports from {a['outlets']} outlets")
    return "\n".join(lines)
