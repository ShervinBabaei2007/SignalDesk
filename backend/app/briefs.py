"""Story briefs: what every outlet agrees on, and where they differ.

Two writers produce the same shape:

* a language model (when ``LLM_ENABLED``), asked to compare the reports using
  only what they say;
* a deterministic extractive fallback that works offline: figures cited by
  several outlets and corroborated key points are "agreement"; outlets whose
  wording is far from the others and figures only one outlet cites are
  "differences".

Briefs are cached per story and rewritten only when the story's reports change.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from . import llm
from .analysis import _clean_sentences, _overlap
from .models import Article, StoryBrief
from .quality import _sections

logger = logging.getLogger("signaldesk.briefs")

MAX_REPORTS = 6          # how many of the best-informed reports feed a brief
SENTIMENT_GAP = 0.3      # how far from the story average counts as "different wording"
_NUMBER = re.compile(r"(?<![\w.])(?:[$€£]\s?)?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|percent|million|billion|trillion|thousand))?",
                     re.IGNORECASE)
_YEAR = re.compile(r"^(?:19|20)\d{2}$")


def member_hash(article_ids) -> str:
    """Order-independent fingerprint of a story's reports, used to detect when its brief is stale."""
    return hashlib.sha1(",".join(str(i) for i in sorted(article_ids)).encode()).hexdigest()


def figures(text: str) -> dict[str, str]:
    """{normalised figure: as written} for the figures worth comparing (no years, tiny numbers or dates)."""
    out: dict[str, str] = {}
    for match in _NUMBER.finditer(text or ""):
        raw = match.group(0).strip()
        norm = re.sub(r"[\s,]", "", raw.lower())
        digits = re.sub(r"\D", "", norm)
        has_unit = bool(re.search(r"[%$€£]|percent|million|billion|trillion|thousand", norm))
        if _YEAR.match(norm) or (len(digits) < 3 and not has_unit):
            continue
        out.setdefault(norm, raw)
    return out


def _text(a: Article) -> str:
    """Best available body text for an article, richest source first."""
    return a.full_text or a.summary_deep or a.summary or ""


def _strip_title(text: str, title: str) -> str:
    """Extracted page text often starts with the headline; it is not a fact."""
    text = text.lstrip()
    if title and text.lower().startswith(title.lower()):
        return text[len(title):].lstrip(" :-\u2013\u2014")
    return text


def _sentences(a: Article) -> list[str]:
    """Clean sentences of an article with the headline stripped off."""
    return _clean_sentences(_strip_title(_text(a), a.title))


def _wording(sentiment: float, gap: float) -> str:
    """Plain-English comparison of an outlet's wording with the other outlets'."""
    if gap > 0:
        return "more positively" if sentiment >= 0 else "less negatively"
    return "less positively" if sentiment > 0 else "more negatively"


def extractive_brief(title: str, members: list[Article]) -> dict[str, Any]:
    """Deterministic brief from the best-informed reports (members must be ranked)."""
    members = members[:MAX_REPORTS]
    by_source: dict[str, Article] = {}
    for m in members:
        by_source.setdefault(m.source, m)  # best report per outlet
    outlets = list(by_source.values())

    sentences = {m.id: _sentences(m) for m in outlets}
    fig_by_outlet = {m.source: figures(_text(m)) for m in outlets}

    agree: list[str] = []

    def add(line: str, store: list[str]) -> None:
        """Append a stripped line to `store` unless it is empty or already present."""
        line = line.strip()
        # skip fragments cut mid-sentence (they start in lowercase) and near-duplicates
        if not line or not (line[0].isupper() or line[0].isdigit() or line[0] in "\"\u201c'$"):
            return
        if all(_overlap(line, existing) < 0.6 for existing in store):
            store.append(line)

    # 1. figures cited by two or more outlets
    shared: dict[str, set[str]] = {}
    for source, figs in fig_by_outlet.items():
        for norm in figs:
            shared.setdefault(norm, set()).add(source)
    for norm, sources in sorted(shared.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(sources) < 2 or len(agree) >= 2:
            break
        raw = next(fig_by_outlet[s][norm] for s in fig_by_outlet if norm in fig_by_outlet[s])
        for m in outlets:
            line = next((s for s in sentences[m.id] if raw in s), None)
            if line:
                add(f"{line} ({len(sources)} outlets cite {raw}.)", agree)
                break

    # 2. key points of the best report that another outlet's report also supports
    if outlets:
        lead = outlets[0]
        key_points = _sections(lead.summary_structured).get("Key points") or sentences[lead.id][:8]
        others = [s for m in outlets[1:] for s in sentences[m.id]]
        for point in key_points:
            if len(agree) >= 4:
                break
            point = _strip_title(point.lstrip("- ").strip(), lead.title)
            if any(_overlap(point, o) >= 0.45 for o in others):
                add(point, agree)
        if not agree:
            fallback = lead.summary_deep or (sentences[lead.id][0] if sentences[lead.id] else "")
            add(fallback or lead.summary or lead.title, agree)

    differ: list[str] = []
    if len(outlets) >= 2:
        avg = sum(m.sentiment for m in outlets) / len(outlets)
        for m in outlets:
            gap = m.sentiment - avg
            if abs(gap) >= SENTIMENT_GAP and len(differ) < 2:
                differ.append(f"{m.source} words this {_wording(m.sentiment, gap)} than the other outlets.")
    if len(outlets) >= 3:
        counts = {norm: len(sources) for norm, sources in shared.items()}
        for m in outlets:
            for norm, raw in fig_by_outlet[m.source].items():
                if counts.get(norm) == 1 and len(differ) < 4:
                    differ.append(f"Only {m.source} cites {raw}.")
                    break
    if not differ:
        differ.append("The outlets largely agree on the facts and the tone." if len(outlets) > 1
                      else "Only one outlet has covered this so far.")
    return {"kind": "auto", "headline": title, "agree": agree, "differ": differ, "model": None}


def build_brief(title: str, members: list[Article]) -> dict[str, Any]:
    """Language-model brief when configured and usable, otherwise the extractive one."""
    if llm.available():
        reports = [
            {"source": m.source, "title": m.title, "text": _text(m)[:1500], "sentiment": m.sentiment}
            for m in members[:MAX_REPORTS]
        ]
        result = llm.story_brief(title=title, reports=reports)
        if result:
            return {"kind": "ai", "headline": result["headline"] or title, "agree": result["agree"],
                    "differ": result["differ"] or ["The reports do not clearly differ."],
                    "model": result.get("model")}
        logger.info("[brief] model brief unavailable, using the extractive fallback")
    return extractive_brief(title, members)


def get_brief(db: Session, cluster_id: int, title: str, members: list[Article], force: bool = False) -> dict[str, Any]:
    """Cached brief for a story; rewritten when its reports change or on request."""
    digest = member_hash(m.id for m in members)
    row = db.get(StoryBrief, cluster_id)
    if row and row.member_hash == digest and not force:
        data = json.loads(row.payload)
        data["generated_at"] = row.created_at
        return data
    data = build_brief(title, members)
    now = datetime.now(timezone.utc)
    payload = json.dumps({k: data[k] for k in ("kind", "headline", "agree", "differ", "model")})
    if row:
        row.member_hash, row.payload, row.created_at = digest, payload, now
    else:
        db.add(StoryBrief(cluster_id=cluster_id, member_hash=digest, payload=payload, created_at=now))
    db.commit()
    data["generated_at"] = now
    return data
