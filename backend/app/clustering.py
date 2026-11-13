"""Story clustering: group headlines that cover the same event.

Different outlets rarely share exact wording, so two articles are linked when
their headlines share enough distinctive words (Jaccard similarity, or a high
overlap with at least three shared terms) and were published close together.
Links are merged transitively (union-find), so A~B and B~C yields one story.

Clustering is computed on demand over a recent window rather than stored:
the window is small (a few hundred headlines), the result is cached until the
article set changes, and nothing needs migrating.
"""

from __future__ import annotations

import re
import threading
from collections import Counter
from html import unescape
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .analysis import STOPWORDS
from .models import Article

WINDOW_DAYS = 3                # only cluster stories this recent
MAX_ARTICLES = 600             # hard cap on the pairwise comparison set
MAX_GAP = timedelta(hours=48)  # items published further apart are different stories
JACCARD_MIN = 0.45
OVERLAP_MIN = 0.6              # |A & B| / min(|A|, |B|), needs MIN_SHARED terms
MIN_SHARED = 3

_WORD = re.compile(r"[a-z0-9][a-z0-9'’]*")
_EXTRA_STOP = {"news", "live", "update", "updates", "breaking", "how", "why", "what", "who",
               "when", "where", "here", "now", "all", "one", "two", "get", "gets", "just"}


def _stem(word: str) -> str:
    word = word.replace("’", "'")
    if word.endswith("'s"):
        word = word[:-2]
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def title_terms(title: str) -> frozenset[str]:
    terms = set()
    for w in _WORD.findall(unescape(title).lower()):
        s = _stem(w)
        if len(s) >= 3 and s not in STOPWORDS and s not in _EXTRA_STOP:
            terms.add(s)
    return frozenset(terms)


def similar(a: frozenset[str], b: frozenset[str]) -> bool:
    shared = len(a & b)
    if not shared:
        return False
    if shared / len(a | b) >= JACCARD_MIN:
        return True
    return shared >= MIN_SHARED and shared / min(len(a), len(b)) >= OVERLAP_MIN


@dataclass(frozen=True)
class Cluster:
    id: int                      # smallest article id in the story (stable as it grows)
    article_ids: tuple[int, ...]
    sources: tuple[str, ...]     # distinct source names, first-seen order
    title: str = ""              # the most representative headline (see _lead)
    lead_id: int = 0             # article that headline belongs to

    @property
    def size(self) -> int:
        return len(self.article_ids)


def _lead(members: list[int], items: list) -> int:
    """Index of the headline most like all the others in the story (the medoid)."""
    def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
        return len(a & b) / len(a | b) if a | b else 0.0

    return max(members, key=lambda m: (sum(jaccard(items[m][1], items[o][1]) for o in members if o != m), -items[m][0]))


def cluster_rows(rows: list[tuple[int, str, str, datetime | None]]) -> list[Cluster]:
    """rows: (id, title, source, published_at). Returns clusters of size >= 2."""
    items = [(i, title_terms(t), s, p) for i, t, s, p in rows]
    parent = list(range(len(items)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            pi, pj = items[i][3], items[j][3]
            if pi and pj and abs(pi - pj) > MAX_GAP:
                continue
            if similar(items[i][1], items[j][1]):
                parent[find(j)] = find(i)

    groups: dict[int, list[int]] = {}
    for idx in range(len(items)):
        groups.setdefault(find(idx), []).append(idx)

    clusters = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda m: items[m][0])
        sources: list[str] = []
        for m in members:
            if items[m][2] not in sources:
                sources.append(items[m][2])
        ids = tuple(items[m][0] for m in members)
        lead = _lead(members, items)
        clusters.append(Cluster(id=ids[0], article_ids=ids, sources=tuple(sources),
                                title=rows[lead][1], lead_id=rows[lead][0]))
    return clusters


_cache: dict = {"key": None, "by_article": {}, "by_id": {}}
_cache_lock = threading.Lock()


def get_clusters(db: Session) -> tuple[dict[int, Cluster], dict[int, Cluster]]:
    """Return ({article_id: Cluster}, {cluster_id: Cluster}) for the recent window."""
    now = datetime.now(timezone.utc)
    count, max_id = db.execute(
        select(func.count(Article.id), func.max(Article.id)).where(Article.is_seed.is_(False))
    ).one()
    key = (count, max_id, now.strftime("%Y%m%d%H"))
    with _cache_lock:
        if _cache["key"] == key:
            return _cache["by_article"], _cache["by_id"]
        cutoff = now - timedelta(days=WINDOW_DAYS)
        rows = db.execute(
            select(Article.id, Article.title, Article.source, Article.published_at)
            .where(Article.is_seed.is_(False),
                   (Article.published_at >= cutoff) | Article.published_at.is_(None))
            .order_by(Article.id.desc())
            .limit(MAX_ARTICLES)
        ).all()
        norm = [(i, t, s, (p.replace(tzinfo=timezone.utc) if p and p.tzinfo is None else p))
                for i, t, s, p in rows]
        clusters = cluster_rows(norm)
        by_article = {aid: c for c in clusters for aid in c.article_ids}
        by_id = {c.id: c for c in clusters}
        _cache.update(key=key, by_article=by_article, by_id=by_id)
        return by_article, by_id


def annotate(db: Session, articles) -> None:
    """Attach cluster_id / cluster_size / cluster_sources to ORM objects in place."""
    by_article, _ = get_clusters(db)
    for a in articles:
        c = by_article.get(a.id)
        a.cluster_id = c.id if c else None
        a.cluster_size = c.size if c else 1
        a.cluster_sources = list(c.sources) if c else []


def to_hrs(dt: datetime | None, now: datetime) -> float:
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max((now - dt).total_seconds() / 3600, 0.0)


HOT_STORIES = 8  # how many top stories count as "hot topics" (list and feed filter agree)


def _ranked(db: Session) -> list[tuple[Cluster, dict]]:
    """The biggest stories right now: covered by several outlets and recent.

    score = (2 x distinct outlets + reports) x 0.5^(age / 24h), so a story that
    many outlets are running today beats a bigger one from two days ago.
    """
    _, by_id = get_clusters(db)
    if not by_id:
        return []
    ids = {i for c in by_id.values() for i in c.article_ids}
    info = {r.id: r for r in db.execute(
        select(Article.id, Article.topic, Article.sentiment, Article.published_at, Article.ingested_at)
        .where(Article.id.in_(ids))).all()}
    now = datetime.now(timezone.utc)
    ranked = []
    for c in by_id.values():
        if len(c.sources) < 2:  # "hot" means more than one outlet is running it
            continue
        members = [info[i] for i in c.article_ids if i in info]
        if not members:
            continue
        stamps = [m.published_at or m.ingested_at for m in members]
        latest = max(stamps, key=lambda d: d if d.tzinfo else d.replace(tzinfo=timezone.utc))
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
            "latest_at": latest if latest.tzinfo else latest.replace(tzinfo=timezone.utc),
        }))
    ranked.sort(key=lambda t: t[0], reverse=True)
    return [(c, story) for _, c, story in ranked]


def trending(db: Session, limit: int = HOT_STORIES) -> list[dict]:
    """The top `limit` hot stories (see _ranked for how they are scored)."""
    return [story for _, story in _ranked(db)[:limit]]


def hot_article_ids(db: Session, limit: int = HOT_STORIES) -> list[int]:
    """Every article that belongs to one of the hot stories."""
    return [i for c, _ in _ranked(db)[:limit] for i in c.article_ids]
