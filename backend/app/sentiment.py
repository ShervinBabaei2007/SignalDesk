"""Sentiment classification: the one place that decides what counts as positive,
negative or neutral.

A score runs from -1.0 to +1.0 (see :func:`app.analysis.score_sentiment`).
Anything above ``POSITIVE_ABOVE`` is positive, anything below ``NEGATIVE_BELOW``
is negative, and the band in between is neutral. The label, the SQL filter, the
stats counts and the digest tone all read the same thresholds, so a score can
never be "positive" in the feed and "neutral" in the stats.
"""

from __future__ import annotations

from typing import Iterable

POSITIVE_ABOVE = 0.15
NEGATIVE_BELOW = -0.15

LABELS = ("positive", "neutral", "negative")


def label(score: float) -> str:
    if score > POSITIVE_ABOVE:
        return "positive"
    if score < NEGATIVE_BELOW:
        return "negative"
    return "neutral"


def conditions(column, wanted: str) -> tuple:
    """SQL conditions (to AND together) selecting rows whose `column` has the `wanted` label."""
    if wanted == "positive":
        return (column > POSITIVE_ABOVE,)
    if wanted == "negative":
        return (column < NEGATIVE_BELOW,)
    if wanted == "neutral":
        return (column >= NEGATIVE_BELOW, column <= POSITIVE_ABOVE)
    raise ValueError(f"unknown sentiment label: {wanted!r}")


def counts(scores: Iterable[float]) -> dict[str, int]:
    """How many scores fall in each label, always with all three keys."""
    out = {name: 0 for name in LABELS}
    for score in scores:
        out[label(score)] += 1
    return out


def tone(avg: float) -> str:
    """Plain-English wording tone for an average score (used in the digest headline)."""
    wanted = label(avg)
    if wanted == "positive":
        return "mostly positive wording"
    if wanted == "negative":
        return "mostly negative wording"
    return "a mix of positive and negative wording"
