"""Story clustering: group headlines that cover the same event.

Different outlets rarely share exact wording, so two articles are linked when
their headlines share enough distinctive words (Jaccard similarity, or a high
overlap with at least three shared terms) and were published close together.
Links are merged transitively (union-find), so A~B and B~C yields one story.

This module is the pure grouping step (headlines in, clusters out). The recent
window, the cache and the story keys live in :mod:`app.story_index`.
"""

from __future__ import annotations

import re
from html import unescape
from dataclasses import dataclass
from datetime import datetime, timedelta


from .analysis import STOPWORDS

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
