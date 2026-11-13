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

    @property
    def size(self) -> int:
        return len(self.article_ids)


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
        clusters.append(Cluster(id=ids[0], article_ids=ids, sources=tuple(sources)))
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
