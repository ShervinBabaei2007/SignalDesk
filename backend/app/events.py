"""Historical event tracking: follow how coverage of an event changes over days or weeks.

A story's cluster id is its smallest article id inside a 3-day window, so it changes as the story
ages and the window slides. An :class:`~app.models.Event` is the durable identity underneath: after
each ingest of the shared data every current cluster is mapped onto an event through the articles it
already shares with one, so a story keeps its history for as long as consecutive windows overlap.
Two events whose stories later turn out to be the same are merged.

:func:`timeline` turns an event into a day-by-day view: reports, outlets, who joined when, and how
the tone moved. A visitor's workspace has no persisted events; its timeline is computed on the fly
from its current cluster, which is enough to show the same view over the window.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from . import story_index
from .clustering import Cluster
from .models import Article, Event, EventArticle
from .story_index import _as_utc


def _when(article) -> datetime:
    """When an article counts as having appeared: its publish time, else when it was ingested."""
    return _as_utc(article.published_at or article.ingested_at)


def assign(db: Session) -> int:
    """Map the current clusters onto persistent events (creating and merging as needed). Returns events touched.

    Only for the shared data: a visitor's session never writes events."""
    if db.info.get("workspace"):
        return 0
    _, by_id = story_index.get_clusters(db)
    if not by_id:
        return 0
    member_ids = {i for c in by_id.values() for i in c.article_ids}
    assigned = dict(db.execute(select(EventArticle.article_id, EventArticle.event_id)
                               .where(EventArticle.article_id.in_(member_ids))).all())
    stamps = {r.id: _when(r) for r in db.execute(
        select(Article.id, Article.published_at, Article.ingested_at).where(Article.id.in_(member_ids))).all()}
    touched = 0
    # Attach each cluster to the event its articles already belong to, merging or creating events as needed.
    for cluster in by_id.values():
        existing = sorted({assigned[i] for i in cluster.article_ids if i in assigned})
        times = [stamps[i] for i in cluster.article_ids if i in stamps]
        if not times:
            continue
        if existing:
            event = db.get(Event, existing[0])
            for other_id in existing[1:]:  # the story now spans events that were thought separate: merge them
                other = db.get(Event, other_id)
                db.execute(update(EventArticle).where(EventArticle.event_id == other_id).values(event_id=event.id))
                event.first_seen = min(_as_utc(event.first_seen), _as_utc(other.first_seen))
                event.last_seen = max(_as_utc(event.last_seen), _as_utc(other.last_seen))
                event.peak_reports = max(event.peak_reports, other.peak_reports)
                db.execute(delete(Event).where(Event.id == other_id))
                # Keep the in-memory map in step with the merge for the clusters still to come.
                for article_id, event_id in list(assigned.items()):
                    if event_id == other_id:
                        assigned[article_id] = event.id
        else:
            event = Event(title=cluster.title, first_seen=min(times), last_seen=max(times), peak_reports=cluster.size)
            db.add(event)
            db.flush()  # assigns event.id, needed for the links below
        # Link the cluster's not-yet-assigned articles to the event.
        for article_id in cluster.article_ids:
            if article_id not in assigned:
                db.add(EventArticle(article_id=article_id, event_id=event.id))
                assigned[article_id] = event.id
        event.title = cluster.title
        event.first_seen = min(_as_utc(event.first_seen), min(times))
        event.last_seen = max(_as_utc(event.last_seen), max(times))
        event.peak_reports = max(event.peak_reports, cluster.size)
        touched += 1
    db.commit()
    return touched


def _event_of(db: Session, cluster: Cluster) -> Event | None:
    """The event a cluster's articles belong to (the one most of them share), or None."""
    rows = db.execute(select(EventArticle.event_id).where(EventArticle.article_id.in_(cluster.article_ids))).scalars().all()
    if not rows:
        return None
    return db.get(Event, max(set(rows), key=rows.count))  # the most common event id among the cluster's articles


def timeline(db: Session, cluster: Cluster) -> dict:
    """Day-by-day coverage of the event a story belongs to (the story's own window when it has no event yet)."""
    event = None if db.info.get("workspace") else _event_of(db, cluster)
    ids = set(cluster.article_ids)
    if event:
        ids |= set(db.execute(select(EventArticle.article_id).where(EventArticle.event_id == event.id)).scalars())
    articles = sorted(
        db.execute(select(Article.id, Article.title, Article.source, Article.sentiment,
                          Article.published_at, Article.ingested_at).where(Article.id.in_(ids))).all(),
        key=lambda r: (_when(r), r.id))
    if not articles:
        return {"event_id": event.id if event else None, "first_seen": None, "last_seen": None, "days_active": 0,
                "reports": 0, "outlets": 0, "peak_reports": 0, "sentiment_shift": 0.0, "first_reported_by": None,
                "days": []}

    by_day: dict[date, list] = {}
    # Bucket the reports by calendar day (UTC), keeping their chronological order.
    for r in articles:
        by_day.setdefault(_when(r).date(), []).append(r)
    first_day, last_day = min(by_day), max(by_day)
    seen: set[str] = set()
    days = []
    # Walk every day from first to last coverage, including quiet days with no reports.
    for offset in range((last_day - first_day).days + 1):
        day = first_day + timedelta(days=offset)
        rows = by_day.get(day, [])
        # Outlets reporting for the first time today, deduplicated in order of appearance.
        new = list(dict.fromkeys(r.source for r in rows if r.source not in seen))
        seen.update(new)
        days.append({
            "date": day.isoformat(), "reports": len(rows), "outlets": len({r.source for r in rows}),
            "new_outlets": new,
            "avg_sentiment": round(sum(r.sentiment for r in rows) / len(rows), 3) if rows else None,
            "headline": rows[0].title if rows else None,
        })
    scored = [d["avg_sentiment"] for d in days if d["avg_sentiment"] is not None]
    return {
        "event_id": event.id if event else None,
        "first_seen": _when(articles[0]), "last_seen": _when(articles[-1]),
        "days_active": len(days), "reports": len(articles), "outlets": len(seen),
        "peak_reports": max(max(d["reports"] for d in days), event.peak_reports if event else 0),
        "sentiment_shift": round(scored[-1] - scored[0], 3) if len(scored) > 1 else 0.0,
        "first_reported_by": articles[0].source,
        "days": days,
    }


def annotate_trending(db: Session, stories: list[dict]) -> list[dict]:
    """Add first_seen and days_active to hot stories that have an event (shared data only)."""
    if db.info.get("workspace") or not stories:
        return stories
    leads = {s["article_id"]: s for s in stories}
    rows = db.execute(select(EventArticle.article_id, Event.first_seen, Event.last_seen)
                      .join(Event, Event.id == EventArticle.event_id)
                      .where(EventArticle.article_id.in_(leads))).all()
    # Copy each tracked event's span onto the hot story it leads.
    for article_id, first, last in rows:
        story = leads[article_id]
        story["first_seen"] = _as_utc(first)
        story["days_active"] = (_as_utc(last).date() - _as_utc(first).date()).days + 1
    return stories
