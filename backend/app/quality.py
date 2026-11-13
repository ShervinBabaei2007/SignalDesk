"""Information score: how much real information a report carries (0-100).

The score is content-based and explainable, and deliberately ignores which
outlet wrote the piece, so it can be used to rank several reports of the same
story fairly. A thin RSS excerpt scores low; a long, fully extracted article
with figures, quotes and a conclusion scores high.

    Depth         35  length of the extracted article text
    Substance     25  numbers, quotes, key points and a bottom line were found
    Analysis      15  written by a language model, or a deep summary exists
    Completeness  10  lead image, publish date, keywords
    Penalty      -10  scraped page boilerplate leaked into the text
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .analysis import has_boilerplate, strip_boilerplate, structured_summary, summarize
from .models import Article

logger = logging.getLogger("signaldesk.quality")

MAX_POINTS = 35 + 25 + 15 + 10
FULL_DEPTH_CHARS = 6000
_SECTION = re.compile(r"^## (.+)$", re.MULTILINE)


def _sections(structured: str | None) -> dict[str, list[str]]:
    """{"Key points": ["bullet", ...], ...} from the '## Heading' / '- bullet' format."""
    out: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in (structured or "").splitlines():
        m = _SECTION.match(line)
        if m:
            current = out.setdefault(m.group(1).strip(), [])
        elif current is not None and line.strip():
            current.append(line.strip())
    return out


def breakdown(a: Any) -> dict[str, float]:
    """Points per factor for an Article-like object (anything with the same attributes)."""
    text_len = len(a.full_text or "")
    if text_len:
        depth = min(text_len / FULL_DEPTH_CHARS, 1.0) * 35
    else:  # only the feed excerpt is known: it can never count as in-depth
        depth = min(len(a.summary or "") / 400, 1.0) * 6

    sections = _sections(a.summary_structured)
    substance = 0.0
    if sections.get("By the numbers"):
        substance += 8
    if sections.get("Notable quotes"):
        substance += 6
    substance += min(len(sections.get("Key points", [])), 6) / 6 * 8
    if sections.get("Bottom line"):
        substance += 3

    if a.analysis_source == "llm":
        analysis = 15.0
    elif a.summary_deep:
        analysis = 8.0
    else:
        analysis = 0.0

    keywords = [k for k in (a.keywords or "").split(",") if k.strip()]
    completeness = (4 if a.image_url else 0) + (3 if a.published_at else 0) + (3 if len(keywords) >= 3 else 0)

    penalty = -10.0 if has_boilerplate(f"{a.summary_deep or ''} {(a.full_text or '')[:800]}") else 0.0

    return {
        "depth": round(depth, 1),
        "substance": round(substance, 1),
        "analysis": analysis,
        "completeness": float(completeness),
        "penalty": penalty,
    }


def information_score(a: Any) -> float:
    """0-100, one decimal."""
    total = max(sum(breakdown(a).values()), 0.0)
    return round(total / MAX_POINTS * 100, 1)


def rank_key(score: float | None, text_len: int, published_ts: float) -> tuple[float, int, float]:
    """Sort key (use reverse=True): best score, then longer text, then newer."""
    return (score or 0.0, text_len, published_ts)


def backfill_info_scores(db: Session, batch: int = 500) -> dict[str, int]:
    """Idempotent startup migration.

    1. Re-derive summaries that still contain scraped boilerplate (lexicon
       analysis only; model-written summaries are left alone).
    2. Score every article that has no information score yet.
    """
    cleaned = 0
    candidates = db.execute(
        select(Article).where(or_(Article.analysis_source.is_(None), Article.analysis_source != "llm"))
    ).scalars().all()
    for article in candidates:
        probe = " ".join(filter(None, [
            article.summary, article.summary_deep, article.summary_structured, (article.full_text or "")[:1500],
        ]))
        if not has_boilerplate(probe):
            continue
        if article.summary:
            article.summary = strip_boilerplate(article.summary)
        if article.full_text:
            article.full_text = strip_boilerplate(article.full_text)
            article.summary_deep = summarize(article.full_text, max_sentences=4, max_chars=500, avoid=article.title)
            article.summary_structured = structured_summary(article.full_text, article.title)
        else:  # only the feed excerpt is known
            base = strip_boilerplate(article.summary or article.title)
            article.summary_deep = summarize(base, max_sentences=3, max_chars=400)
            article.summary_structured = structured_summary(base, article.title)
        article.info_score = None  # rescore below
        cleaned += 1

    scored = 0
    while True:
        rows = db.execute(select(Article).where(Article.info_score.is_(None)).limit(batch)).scalars().all()
        if not rows:
            break
        for article in rows:
            article.info_score = information_score(article)
            scored += 1
        db.commit()
    if cleaned:
        db.commit()
        logger.info("[migrate] re-derived %s summaries that contained page boilerplate", cleaned)
    return {"cleaned": cleaned, "scored": scored}
