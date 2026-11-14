"""The story index: which reports make up which story, right now.

Stories are computed on demand over a recent window rather than stored: the
window is small (a few hundred headlines), the grouping (see
:mod:`app.clustering`) is cached until the article set changes, and nothing
needs migrating. This module owns everything that depends on that window:

* the window itself (``_window``) and its cache,
* story keys (``c<cluster id>`` for a clustered story, ``a<article id>`` for a lone report),
* ``recent_stories``: [(key, member articles)] for the feed and the watchlist,
* ``annotate``: attach cluster fields to articles,
* hot ranking: which stories the most outlets are covering right now.
"""

from __future__ import annotations

import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from .clustering import Cluster, cluster_rows
from .models import Article

WINDOW_DAYS = 3                # only group stories this recent
MAX_ARTICLES = 600             # hard cap on the pairwise comparison set
HOT_STORIES = 8                # how many top stories count as "hot topics" (list and feed filter agree)


class StoryKey(NamedTuple):
    """Identifier of a story: a cluster ('c') or a lone report ('a')."""
    kind: str   # 'c' = clustered story, 'a' = lone report
    id: int

    @property
    def is_cluster(self) -> bool:
        """True when the key refers to a clustered story."""
        return self.kind == "c"

    def __str__(self) -> str:
        """Render the key as the string used by the API."""
        return f"{self.kind}{self.id}"

    @classmethod
    def parse(cls, key: str) -> "StoryKey":
        """Parse a key string such as 'c12' or 'a7'."""
        return cls(key[0], int(key[1:]))

    @classmethod
    def of(cls, cluster: Cluster | None, article_id: int) -> "StoryKey":
        """Key for a cluster, or for a lone article when it has none."""
        return cls("c", cluster.id) if cluster else cls("a", article_id)


def story_key(cluster: Cluster | None, article_id: int) -> str:
    """Stable string key of a story (what the API and the watchlist store)."""
    return str(StoryKey.of(cluster, article_id))


def parse_story_key(key: str) -> StoryKey:
    """Parse a story key string."""
    return StoryKey.parse(key)


def _window(now: datetime) -> tuple[ColumnElement, ...]:
    """WHERE conditions for the recent, non-seed reports that stories are built from."""
    cutoff = now - timedelta(days=WINDOW_DAYS)
    return (Article.is_seed.is_(False),
            (Article.published_at >= cutoff) | Article.published_at.is_(None))


_CACHE_SIZE = 64  # workspaces cached at once; the oldest is dropped first
_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def reset_cache() -> None:
    """Forget the cached grouping (tests, and anything that edits articles in place)."""
    with _cache_lock:
        _cache.clear()


def get_clusters(db: Session) -> tuple[dict[int, Cluster], dict[int, Cluster]]:
    """Return ({article_id: Cluster}, {cluster_id: Cluster}) for the recent window."""
    return _load(db)[:2]


def _load(db: Session) -> tuple[dict[int, Cluster], dict[int, Cluster], list[int]]:
    """Compute or fetch the cached clusters for the recent window."""
    now = datetime.now(timezone.utc)
    workspace = db.info.get("workspace", "")  # the session only sees the base data plus its own articles
    count, max_id = db.execute(
        select(func.count(Article.id), func.max(Article.id)).where(Article.is_seed.is_(False))
    ).one()
    key = (count, max_id, now.strftime("%Y%m%d%H"))
    with _cache_lock:
        entry = _cache.get(workspace)
        if entry and entry["key"] == key:
            return entry["by_article"], entry["by_id"], entry["window_ids"]
        rows = db.execute(
            select(Article.id, Article.title, Article.source, Article.published_at)
            .where(*_window(now))
            .order_by(Article.id.desc())
            .limit(MAX_ARTICLES)
        ).all()
        clusters = cluster_rows([(i, t, s, _as_utc(p)) for i, t, s, p in rows])
        by_article = {aid: c for c in clusters for aid in c.article_ids}
        by_id = {c.id: c for c in clusters}
        window_ids = [r[0] for r in rows]
        _cache.pop(workspace, None)
        _cache[workspace] = {"key": key, "by_article": by_article, "by_id": by_id, "window_ids": window_ids}
        while len(_cache) > _CACHE_SIZE:
            _cache.pop(next(iter(_cache)))
        return by_article, by_id, window_ids


def recent_stories(db: Session) -> list[tuple[str, list[Article]]]:
    """[(story key, member articles)] for the recent window, newest ids first.

    Built from the same cached window as :func:`get_clusters`, so a story's key
    here always matches the key the feed gives it.
    """
    by_article, _, window_ids = _load(db)
    articles = {a.id: a for a in db.execute(
        select(Article).where(Article.id.in_(window_ids or [0]))).scalars()}
    groups: dict[str, list[Article]] = {}
    for article_id in window_ids:
        a = articles.get(article_id)
        if a is not None:
            groups.setdefault(story_key(by_article.get(article_id), article_id), []).append(a)
    return list(groups.items())


def annotate(db: Session, articles) -> None:
    """Attach cluster_id / cluster_size / cluster_sources to ORM objects in place."""
    by_article, _ = get_clusters(db)
    for a in articles:
        c = by_article.get(a.id)
        a.cluster_id = c.id if c else None
        a.cluster_size = c.size if c else 1
        a.cluster_sources = list(c.sources) if c else []


def _as_utc(dt: datetime | None) -> datetime | None:
    """Treat naive timestamps (as SQLite returns them) as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def to_hrs(dt: datetime | None, now: datetime) -> float:
    """Hours between a datetime and now, never negative."""
    if dt is None:
        return 0.0
    return max((now - _as_utc(dt)).total_seconds() / 3600, 0.0)


def rank_hot(clusters, info: dict, now: datetime) -> list[tuple[Cluster, dict]]:
    """The biggest stories right now: covered by several outlets and recent.

    score = (2 x distinct outlets + reports) x 0.5^(age / 24h), so a story that
    many outlets are running today beats a bigger one from two days ago.
    `info` maps article id -> an object with topic, sentiment, published_at, ingested_at.
    Pure: no database, so the scoring is testable on plain data.
    """
    ranked = []
    for c in clusters:
        if len(c.sources) < 2:  # "hot" means more than one outlet is running it
            continue
        members = [info[i] for i in c.article_ids if i in info]
        if not members:
            continue
        stamps = [_as_utc(m.published_at or m.ingested_at) for m in members]
        latest = max(stamps)
        age = min(to_hrs(d, now) for d in stamps)
        score = (len(c.sources) * 2 + c.size) * 0.5 ** (age / 24)
        ranked.append((score, c, {
            "cluster_id": c.id,
            "article_id": c.lead_id,
            "title": c.title,
            "reports": c.size,
            "outlets": len(c.sources),
            "sources": list(c.sources),
            "topic": Counter(m.topic for m in members).most_common(1)[0][0],
            "avg_sentiment": round(sum(m.sentiment for m in members) / len(members), 3),
            "latest_at": latest,
        }))
    ranked.sort(key=lambda t: t[0], reverse=True)
    return [(c, story) for _, c, story in ranked]


def _ranked(db: Session) -> list[tuple[Cluster, dict]]:
    """Cached list of hot clusters with their story data."""
    _, by_id = get_clusters(db)
    if not by_id:
        return []
    ids = {i for c in by_id.values() for i in c.article_ids}
    info = {r.id: r for r in db.execute(
        select(Article.id, Article.topic, Article.sentiment, Article.published_at, Article.ingested_at)
        .where(Article.id.in_(ids))).all()}
    return rank_hot(by_id.values(), info, datetime.now(timezone.utc))


def trending(db: Session, limit: int = HOT_STORIES) -> list[dict]:
    """The top `limit` hot stories (see :func:`rank_hot` for how they are scored)."""
    return [story for _, story in _ranked(db)[:limit]]


def hot_article_ids(db: Session, limit: int = HOT_STORIES) -> list[int]:
    """Every article that belongs to one of the hot stories."""
    return [i for c, _ in _ranked(db)[:limit] for i in c.article_ids]
