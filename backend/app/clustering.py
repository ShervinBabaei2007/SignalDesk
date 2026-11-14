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
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape

import numpy as np

from . import config
from .analysis import STOPWORDS

MAX_GAP = timedelta(hours=48)  # items published further apart are different stories
JACCARD_MIN = 0.45
OVERLAP_MIN = 0.6              # |A & B| / min(|A|, |B|), needs MIN_SHARED terms
MIN_SHARED = 3
MAX_CLUSTER = 25               # a bigger group is a sign of chaining and is split with a stricter threshold
SPLIT_STEP = 0.04

_WORD = re.compile(r"[a-z0-9][a-z0-9'’]*")
_EXTRA_STOP = {"news", "live", "update", "updates", "breaking", "how", "why", "what", "who",
               "when", "where", "here", "now", "all", "one", "two", "get", "gets", "just"}


def _stem(word: str) -> str:
    """Reduce a word to a crude stem so plurals and simple inflections compare equal."""
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
    """Distinctive stemmed words of a headline, used to compare headlines for similarity."""
    terms = set()
    for w in _WORD.findall(unescape(title).lower()):
        s = _stem(w)
        if len(s) >= 3 and s not in STOPWORDS and s not in _EXTRA_STOP:
            terms.add(s)
    return frozenset(terms)


def similar(a: frozenset[str], b: frozenset[str]) -> bool:
    """True when two headline term sets are close enough to be the same event."""
    shared = len(a & b)
    if not shared:
        return False
    if shared / len(a | b) >= JACCARD_MIN:
        return True
    return shared >= MIN_SHARED and shared / min(len(a), len(b)) >= OVERLAP_MIN


@dataclass(frozen=True)
class Cluster:
    """One story: a group of article ids covering the same event, with its lead headline and outlets."""
    id: int                      # smallest article id in the story (stable as it grows)
    article_ids: tuple[int, ...]
    sources: tuple[str, ...]     # distinct source names, first-seen order
    title: str = ""              # the most representative headline (see _lead)
    lead_id: int = 0             # article that headline belongs to

    @property
    def size(self) -> int:
        """Number of reports in the story."""
        return len(self.article_ids)


def _lead(members: list[int], items: list) -> int:
    """Index of the headline most like all the others in the story (the medoid)."""
    def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
        """Jaccard similarity of two term sets."""
        return len(a & b) / len(a | b) if a | b else 0.0

    return max(members, key=lambda m: (sum(jaccard(items[m][1], items[o][1]) for o in members if o != m), -items[m][0]))


def _group(items: list, indices: list[int], sim_min: float, unit: dict[int, np.ndarray]) -> list[list[int]]:
    """Union-find over `indices`: link headlines that overlap in words, or whose vectors are close in meaning."""
    parent = {i: i for i in indices}

    def find(x: int) -> int:
        """Union-find root lookup with path compression."""
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    embedded = [i for i in indices if items[i][0] in unit]
    cosine = {}
    if len(embedded) > 1:  # one matrix product for every pair of embedded headlines
        matrix = np.stack([unit[items[i][0]] for i in embedded])
        sims = matrix @ matrix.T
        cosine = {(embedded[a], embedded[b]): float(sims[a, b])
                  for a in range(len(embedded)) for b in range(a + 1, len(embedded))}

    for a, i in enumerate(indices):
        for j in indices[a + 1:]:
            pi, pj = items[i][3], items[j][3]
            if pi and pj and abs(pi - pj) > MAX_GAP:
                continue
            if similar(items[i][1], items[j][1]) or cosine.get((i, j), 0.0) >= sim_min:
                parent[find(j)] = find(i)

    groups: dict[int, list[int]] = {}
    for idx in indices:
        groups.setdefault(find(idx), []).append(idx)
    return list(groups.values())


def _split_chains(items: list, groups: list[list[int]], unit: dict[int, np.ndarray]) -> list[list[int]]:
    """Re-cluster any oversized group with a stricter meaning threshold until it breaks into sane stories."""
    result: list[list[int]] = []
    for members in groups:
        if len(members) <= MAX_CLUSTER or not unit:
            result.append(members)
            continue
        threshold, parts = config.EMBED_SIM_MIN, [members]
        while threshold < 0.98 and any(len(p) > MAX_CLUSTER for p in parts):
            threshold += SPLIT_STEP
            parts = _group(items, members, threshold, unit)
        result.extend(parts)  # best effort: a group that still will not split is kept as it is
    return result


def cluster_rows(rows: list[tuple[int, str, str, datetime | None]],
                 vectors: dict[int, np.ndarray] | None = None) -> list[Cluster]:
    """rows: (id, title, source, published_at). Returns clusters of size >= 2.

    `vectors` maps article id to a unit-length embedding. Headlines with vectors can also be linked by
    meaning; headlines without them are grouped by words only, so a partly embedded corpus works.
    """
    items = [(i, title_terms(t), s, p) for i, t, s, p in rows]
    unit = vectors or {}
    groups = _split_chains(items, _group(items, list(range(len(items))), config.EMBED_SIM_MIN, unit), unit)

    clusters = []
    for members in groups:
        if len(members) < 2:
            continue
        members.sort(key=lambda m: items[m][0])
        sources = tuple(dict.fromkeys(items[m][2] for m in members))  # distinct, first-seen order
        ids = tuple(items[m][0] for m in members)
        lead = _lead(members, items)
        clusters.append(Cluster(id=ids[0], article_ids=ids, sources=sources,
                                title=rows[lead][1], lead_id=rows[lead][0]))
    return clusters
