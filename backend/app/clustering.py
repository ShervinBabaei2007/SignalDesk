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
JACCARD_MIN = 0.45             # |A & B| / |A | B| at or above this links two headlines
OVERLAP_MIN = 0.6              # |A & B| / min(|A|, |B|), needs MIN_SHARED terms
MIN_SHARED = 3
MAX_CLUSTER = 25               # a bigger group is a sign of chaining and is split with a stricter threshold
SPLIT_STEP = 0.04              # how much the meaning threshold rises per split attempt

_WORD = re.compile(r"[a-z0-9][a-z0-9'’]*")  # words and numbers, keeping straight or curly apostrophes
# Headline filler words that say nothing about which event it is
_EXTRA_STOP = {"news", "live", "update", "updates", "breaking", "how", "why", "what", "who",
               "when", "where", "here", "now", "all", "one", "two", "get", "gets", "just"}


def _stem(word: str) -> str:
    """Reduce a word to a crude stem so plurals and simple inflections compare equal."""
    word = word.replace("’", "'")
    if word.endswith("'s"):  # possessive
        word = word[:-2]
    if len(word) > 4 and word.endswith("ies"):  # "companies" -> "company"
        return word[:-3] + "y"
    # Length guards keep short words like "king" or "bed" intact.
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):  # plural, but not "class"
        return word[:-1]
    return word


def title_terms(title: str) -> frozenset[str]:
    """Distinctive stemmed words of a headline, used to compare headlines for similarity."""
    terms = set()
    # Keep stems of 3+ letters that are not stopwords.
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
    # A short headline contained in a longer one still matches if enough terms are shared.
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

    # Highest total similarity to the other headlines wins; ties go to the smallest article id.
    return max(members, key=lambda m: (sum(jaccard(items[m][1], items[o][1]) for o in members if o != m), -items[m][0]))


def _group(items: list, indices: list[int], sim_min: float, unit: dict[int, np.ndarray]) -> list[list[int]]:
    """Union-find over `indices`: link headlines that overlap in words, or whose vectors are close in meaning."""
    parent = {i: i for i in indices}

    def find(x: int) -> int:
        """Union-find root lookup with path compression."""
        # Walk up to the root, pointing each node at its grandparent along the way.
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

    # Compare every pair once and merge the ones that are close in time and in words or meaning.
    for a, i in enumerate(indices):
        for j in indices[a + 1:]:
            pi, pj = items[i][3], items[j][3]
            if pi and pj and abs(pi - pj) > MAX_GAP:  # an unknown date never rules a pair out
                continue
            if similar(items[i][1], items[j][1]) or cosine.get((i, j), 0.0) >= sim_min:
                parent[find(j)] = find(i)

    groups: dict[int, list[int]] = {}
    # Bucket every index under its root to form the groups.
    for idx in indices:
        groups.setdefault(find(idx), []).append(idx)
    return list(groups.values())


def _split_chains(items: list, groups: list[list[int]], unit: dict[int, np.ndarray]) -> list[list[int]]:
    """Re-cluster any oversized group with a stricter meaning threshold until it breaks into sane stories."""
    result: list[list[int]] = []
    # Leave normal groups alone; without vectors there is no stricter threshold to apply.
    for members in groups:
        if len(members) <= MAX_CLUSTER or not unit:
            result.append(members)
            continue
        threshold, parts = config.EMBED_SIM_MIN, [members]
        # Raise the threshold step by step (stopping short of near-identical, 0.98) until every part is small.
        while threshold < 0.98 and any(len(p) > MAX_CLUSTER for p in parts):
            threshold += SPLIT_STEP
            parts = _group(items, members, threshold, unit)
        result.extend(parts)  # best effort: a group that still will not split is kept as it is
    return result


def cluster_rows(rows: list[tuple[int, str, str, datetime | None]],
                 vectors: dict[int, np.ndarray] | None = None) -> list[Cluster]:
    """Group (id, title, source, published_at) rows into stories, returning clusters of size >= 2.

    `vectors` maps article id to a unit-length embedding. Headlines with vectors can also be linked by
    meaning; headlines without them are grouped by words only, so a partly embedded corpus works.
    """
    items = [(i, title_terms(t), s, p) for i, t, s, p in rows]
    unit = vectors or {}
    groups = _split_chains(items, _group(items, list(range(len(items))), config.EMBED_SIM_MIN, unit), unit)

    clusters = []
    # Turn each multi-report group into a Cluster ordered by article id.
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
