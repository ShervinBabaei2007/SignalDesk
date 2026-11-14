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

This module also owns the watch rules (create, pause, remove). It raises
:class:`WatchError`; the HTTP layer maps that to a status code.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clustering, notifications
from .analysis import TOPIC_EMOJI
from .models import Article, Watch, WatchAlert

logger = logging.getLogger("signaldesk.watches")

MAX_WATCHES = 25


class WatchError(Exception):
    """A watch rule was broken. `kind` is 'invalid', 'conflict' or 'not_found'."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def term_matches(term: str, text: str) -> bool:
    """Whole-word / whole-phrase, case-insensitive ('AI' does not match 'said')."""
    return bool(re.search(rf"(?<!\w){re.escape(term.strip())}(?!\w)", text, re.IGNORECASE))


def story_text(members: list[Article]) -> str:
    return " ".join(f"{m.title} {m.summary or ''}" for m in members)


def matches(watch: Watch, members: list[Article]) -> bool:
    if watch.topic and not any(m.topic == watch.topic for m in members):
        return False
    return term_matches(watch.term, story_text(members))


def story_matches(watch: Watch, members: list[Article]) -> bool:
    """The one rule for "this watch fires on this story": enough outlets, and the term/topic match."""
    return len({m.source for m in members}) >= watch.min_outlets and matches(watch, members)


def matching_terms(watches: list[Watch], members: list[Article]) -> list[str]:
    """Terms of the active watches that this story matches (for the feed badge)."""
    return [w.term for w in watches if w.is_active and matches(w, members)]


def active(db: Session) -> list[Watch]:
    return list(db.execute(select(Watch).where(Watch.is_active.is_(True)).order_by(Watch.id)).scalars())


def recent_stories(db: Session) -> list[tuple[str, list[Article]]]:
    """[(story key, member articles)] for the recent window; keys match the feed's story keys."""
    return clustering.recent_stories(db)


def _headline(key: str, members: list[Article], by_id: dict) -> tuple[str, int | None, int]:
    """(title, cluster id, lead article id) for an alert."""
    kind, ident = clustering.parse_story_key(key)
    if kind == "c":
        cluster = by_id.get(ident)
        if cluster is not None:
            return cluster.title, cluster.id, cluster.lead_id
    return members[0].title, None, members[0].id


def matching_stories(db: Session, watch: Watch) -> list[tuple[str, list[Article]]]:
    return [(key, members) for key, members in recent_stories(db) if story_matches(watch, members)]


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


def deliver_to_channels(alerts: list[dict]) -> bool:
    """Default delivery adapter: Slack/email, when any channel is configured. True if it was sent."""
    if not notifications.configured_channels():
        return False
    return bool(notifications.deliver_alert(alert_subject(alerts), alert_text(alerts))["sent"])


def check_watches(db: Session, deliver: bool = True,
                  notify: Callable[[list[dict]], bool] | None = None) -> list[dict]:
    """Raise one alert per (watch, story) that newly matches. Returns the new alerts.

    `notify` is the delivery seam: it receives the new alerts and returns True when they
    were delivered. Only those exact (watch, story) alerts are then marked notified.
    """
    watches = active(db)
    if not watches:
        return []
    _, by_id = clustering.get_clusters(db)
    stories = recent_stories(db)
    alerts: list[dict] = []
    for watch in watches:
        seen = {k for (k,) in db.execute(select(WatchAlert.story_key).where(WatchAlert.watch_id == watch.id))}
        for key, members in stories:
            if key in seen or not story_matches(watch, members):
                continue
            title, cluster_id, article_id = _headline(key, members, by_id)
            db.add(WatchAlert(watch_id=watch.id, story_key=key, notified=False))
            alerts.append({
                "watch_id": watch.id, "term": watch.term, "story_key": key, "cluster_id": cluster_id,
                "article_id": article_id, "title": title, "outlets": len({m.source for m in members}),
                "reports": len(members),
            })
    if alerts:
        db.commit()
        if deliver and (notify or deliver_to_channels)(alerts):
            pairs = {(a["watch_id"], a["story_key"]) for a in alerts}
            for row in db.execute(
                select(WatchAlert).where(WatchAlert.notified.is_(False),
                                         WatchAlert.watch_id.in_({w for w, _ in pairs}),
                                         WatchAlert.story_key.in_({k for _, k in pairs}))
            ).scalars():
                if (row.watch_id, row.story_key) in pairs:
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


# --------------------------------------------------------------------------- #
# Rules: creating, pausing and removing watches
# --------------------------------------------------------------------------- #

def all_watches(db: Session) -> list[Watch]:
    return list(db.execute(select(Watch).order_by(Watch.id)).scalars())


def with_counts(db: Session, rows: list[Watch]) -> list[Watch]:
    """Set `.matches` on each watch: how many recent stories it fires on right now."""
    stories = recent_stories(db)
    for w in rows:
        w.matches = sum(1 for _, members in stories if story_matches(w, members))
    return rows


def create(db: Session, term: str, topic: str | None, min_outlets: int) -> Watch:
    term = " ".join(term.split())
    topic = (topic or "").strip() or None
    if not term:
        raise WatchError("invalid", "A watch needs a word or phrase")
    if topic and topic not in TOPIC_EMOJI:
        raise WatchError("invalid", f"topic must be one of: {', '.join(TOPIC_EMOJI)}")
    existing = all_watches(db)
    if len(existing) >= MAX_WATCHES:
        raise WatchError("conflict", f"You can watch up to {MAX_WATCHES} terms; remove one first")
    if any(w.term.lower() == term.lower() and w.topic == topic for w in existing):
        raise WatchError("conflict", "You are already watching that")
    watch = Watch(term=term, topic=topic, min_outlets=min_outlets, is_active=True)
    db.add(watch)
    db.commit()
    db.refresh(watch)
    baseline(db, watch)  # today's matches are not "news": only later stories alert
    return watch


def _get(db: Session, watch_id: int) -> Watch:
    watch = db.get(Watch, watch_id)
    if not watch:
        raise WatchError("not_found", "Watch not found")
    return watch


def set_active(db: Session, watch_id: int, is_active: bool) -> Watch:
    watch = _get(db, watch_id)
    if is_active and not watch.is_active:
        baseline(db, watch)  # resuming should not replay what happened while paused
    watch.is_active = is_active
    db.commit()
    db.refresh(watch)
    return watch


def remove(db: Session, watch_id: int) -> None:
    watch = _get(db, watch_id)
    for row in db.execute(select(WatchAlert).where(WatchAlert.watch_id == watch_id)).scalars():
        db.delete(row)
    db.delete(watch)
    db.commit()
