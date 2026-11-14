"""Claim-level comparison: which factual claims the outlets agree on, and where they disagree.

A story brief says what the reports share in general terms; this goes down to individual claims.
Two writers produce the same shape, like :mod:`app.briefs`:

* a language model (when one is configured), asked to extract and judge claims using only the reports;
* a deterministic extractive fallback that works offline. It keeps the checkable sentences of each
  report (figures, quotes, attributed statements), matches the same claim across outlets by wording,
  and flags a claim as disputed when two outlets give different figures for it.

Each claim is **agreed** (two or more outlets make it), **disputed** (outlets give conflicting figures)
or **single** (only one outlet says it, shown only when it carries a figure). Results are cached with
the story brief and rewritten only when the story's reports change.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from . import llm
from .analysis import _overlap
from .briefs import MAX_REPORTS, _sentences, _text, figures, member_hash
from .models import Article, StoryBrief

logger = logging.getLogger("signaldesk.claims")

MATCH_MIN = 0.5            # word overlap at which two sentences are the same claim
FIGURE_TOLERANCE = 0.05    # figures within 5% of each other are the same figure
MAX_PER_REPORT = 12        # checkable sentences kept per report
MAX_CLAIMS = 10
MAX_SINGLE = 3
STATUSES = ("agreed", "disputed", "single")

_QUOTE = re.compile(r"[\"“”][^\"“”]{12,}[\"“”]")
_ATTRIBUTION = re.compile(
    r"\b(said|says|announced|confirmed|reported|according to|told|warned|estimated|expects?|plans?|"
    r"will|has been|have been|killed|injured|arrested|approved|signed|rose|fell|raised|cut)\b", re.IGNORECASE)
_ENTITIES = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")
_MULTIPLIER = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}


def figure_value(raw: str) -> tuple[str, float] | None:
    """(unit class, magnitude) of a figure as written: '$4.2 billion' -> ('money', 4.2e9)."""
    lowered = raw.lower()
    number = re.search(r"\d[\d,]*(?:\.\d+)?", lowered)
    if not number:
        return None
    value = float(number.group(0).replace(",", ""))
    for word, factor in _MULTIPLIER.items():
        if word in lowered:
            value *= factor
    unit = "pct" if ("%" in lowered or "percent" in lowered) else "money" if re.search(r"[$€£]", lowered) else "num"
    return unit, value


def is_checkable(sentence: str) -> bool:
    """A sentence worth comparing: it states a figure, quotes someone, or attributes a statement to a named party."""
    if figures(sentence) or _QUOTE.search(sentence):
        return True
    return bool(_ATTRIBUTION.search(sentence)) and len(_ENTITIES.findall(sentence)) >= 2


def _words(sentence: str) -> str:
    """The sentence without its figures, so the same claim with different numbers still matches."""
    return re.sub(r"[$€£]?\d[\d,]*(?:\.\d+)?\s?(?:%|percent|million|billion|trillion|thousand)?", " ", sentence)


def _conflict(per_outlet: dict[str, dict[str, str]]) -> dict[str, str] | None:
    """Each outlet's figure when two outlets give different figures of the same kind, else None."""
    parsed: dict[str, dict[str, tuple[str, float]]] = {}
    for outlet, figs in per_outlet.items():
        for raw in figs.values():
            val = figure_value(raw)
            if val:
                parsed.setdefault(val[0], {}).setdefault(outlet, (raw, val[1]))
    for by_outlet in parsed.values():
        if len(by_outlet) < 2:
            continue
        values = list(by_outlet.values())
        if all(abs(a[1] - b[1]) > FIGURE_TOLERANCE * max(abs(a[1]), abs(b[1]), 1e-9)
               for i, a in enumerate(values) for b in values[i + 1:]):
            return {outlet: raw for outlet, (raw, _) in by_outlet.items()}
    return None


def extractive_claims(title: str, members: list[Article]) -> list[dict[str, Any]]:
    """Deterministic claim comparison (members must be ranked best first)."""
    best: dict[str, Article] = {}
    for m in members[:MAX_REPORTS]:
        best.setdefault(m.source, m)  # the best report per outlet
    groups: list[dict[str, Any]] = []
    for outlet, report in best.items():
        picked = [s for s in _sentences(report) if is_checkable(s)][:MAX_PER_REPORT]
        for sentence in picked:
            for group in groups:
                if outlet not in group["by_outlet"] and _overlap(_words(sentence), _words(group["text"])) >= MATCH_MIN:
                    group["by_outlet"][outlet] = sentence
                    break
            else:
                groups.append({"text": sentence, "by_outlet": {outlet: sentence}})

    claims = []
    for group in groups:
        outlets = list(group["by_outlet"])
        values = _conflict({o: figures(s) for o, s in group["by_outlet"].items()}) if len(outlets) > 1 else None
        if values:
            status = "disputed"
        elif len(outlets) > 1:
            status = "agreed"
        elif figures(group["text"]):
            status = "single"
        else:
            continue  # a lone sentence without a figure is noise, not a claim worth showing
        claims.append({"text": group["text"], "status": status, "outlets": outlets, "values": values})
    order = {"disputed": 0, "agreed": 1, "single": 2}
    claims.sort(key=lambda c: (order[c["status"]], -len(c["outlets"])))
    kept, singles = [], 0
    for claim in claims:
        if claim["status"] == "single":
            singles += 1
            if singles > MAX_SINGLE:
                continue
        kept.append(claim)
    return kept[:MAX_CLAIMS]


def normalize_claims(data: Any, known_outlets: set[str]) -> list[dict[str, Any]] | None:
    """Validate raw model JSON for a claim list; None when it is unusable."""
    items = data.get("claims") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = llm._clean_str(item.get("text"), 320)
        status = item.get("status")
        outlets = [o for o in llm._clean_list(item.get("outlets"), 8, 80) if o in known_outlets]
        if not text or status not in STATUSES or not outlets:
            continue
        raw_values = item.get("values") if isinstance(item.get("values"), dict) else {}
        values = {o: llm._clean_str(v, 60) for o, v in raw_values.items() if o in known_outlets and llm._clean_str(v, 60)}
        out.append({"text": text, "status": status, "outlets": outlets,
                    "values": values if status == "disputed" and len(values) >= 2 else None})
    return out[:MAX_CLAIMS] or None


def build_claims(title: str, members: list[Article]) -> dict[str, Any]:
    """Language-model claims when configured and usable, otherwise the extractive ones.

    The model is only used when every report is shared data: a visitor's own articles never spend the owner's quota.
    """
    shared_only = not any(getattr(m, "workspace_id", "") for m in members)
    if llm.available() and shared_only:
        reports = [{"source": m.source, "title": m.title, "text": _text(m)[:1500], "sentiment": m.sentiment}
                   for m in members[:MAX_REPORTS]]
        result = llm.story_claims(title=title, reports=reports)
        if result:
            claims = normalize_claims(result, {m.source for m in members[:MAX_REPORTS]})
            if claims:
                return {"kind": "ai", "items": claims}
        logger.info("[claims] model claims unavailable, using the extractive fallback")
    return {"kind": "auto", "items": extractive_claims(title, members)}


def get_claims(db: Session, cluster_id: int, title: str, members: list[Article], force: bool = False) -> dict[str, Any]:
    """Cached claims for a story; rewritten when its reports change or on request.

    Stored on the story's brief row (so it is invalidated by the same fingerprint)."""
    if any(getattr(m, "workspace_id", "") for m in members):
        return build_claims(title, members)  # a visitor's story is never cached where others could read it
    row = db.get(StoryBrief, cluster_id)
    digest = member_hash(m.id for m in members)
    if row and row.claims and row.member_hash == digest and not force:
        try:
            return json.loads(row.claims)
        except json.JSONDecodeError:
            pass
    data = build_claims(title, members)
    if row and row.member_hash == digest:
        row.claims = json.dumps(data)
        db.commit()
    return data
