"""Stories: one card per event, with the best-informed report on top.

Several outlets usually cover the same event. Instead of listing each report
separately, the feed groups them (see :mod:`app.story_index`) and orders the
reports inside each story by how much real information they carry (see
:mod:`app.quality`): best score first, then longer text, then newer.

The filtering and ordering helpers are shared with the flat ``/api/articles``
endpoint so both always agree on what "matches".
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from . import briefs, claims, reliability, story_index, watches
from . import sentiment as sentiment_scale
from .clustering import Cluster
from .models import Article
from .quality import _sections

SENTIMENTS = sentiment_scale.LABELS
ORDERS = ("newest", "oldest", "sentiment_high", "sentiment_low", "info")
MAX_IDS = 200


def parse_ids(raw: str | None) -> list[int] | None:
    """'1,2,3' -> [1, 2, 3]; None when absent. Bad input is a 422, not a 500."""
    if raw is None or not raw.strip():
        return None
    try:
        ids = [int(part) for part in raw.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(422, "ids must be a comma-separated list of integers") from None
    return ids[:MAX_IDS]


def clean(value: str | None) -> str | None:
    """Tolerate empty query strings (?sentiment=) from clients."""
    return (value or "").strip() or None


def validate(sentiment: str | None, order: str) -> str:
    """Check the sentiment and order parameters (422 on bad values) and return the normalised order."""
    if sentiment and sentiment not in SENTIMENTS:
        raise HTTPException(422, "sentiment must be positive, neutral, or negative")
    order = (order or "newest").strip().lower()
    if order not in ORDERS:
        raise HTTPException(422, "order must be newest, oldest, sentiment_high, sentiment_low, or info")
    return order


def apply_filters(
    db: Session,
    q: Select,
    *,
    search: str | None,
    source: str | None,
    topic: str | None,
    sentiment: str | None,
    cluster: int | None,
    hot: bool,
    ids: list[int] | None,
) -> Select:
    """Apply the shared feed filters (search, topic, sentiment, source, etc.) to a query."""
    if search:
        like = f"%{search}%"
        q = q.where(Article.title.ilike(like) | Article.summary.ilike(like))
    if source:
        q = q.where(Article.source == source)
    if topic:
        q = q.where(Article.topic == topic)
    if sentiment in sentiment_scale.LABELS:
        q = q.where(*sentiment_scale.conditions(Article.sentiment, sentiment))
    if hot:
        q = q.where(Article.id.in_(story_index.hot_article_ids(db) or [0]))
    if cluster is not None:
        _, by_id = story_index.get_clusters(db)
        story = by_id.get(cluster)
        q = q.where(Article.id.in_(story.article_ids if story else [0]))
    if ids is not None:
        q = q.where(Article.id.in_(ids or [0]))
    return q


def ordering(order: str) -> tuple:
    """SQL ordering clauses for a named sort order."""
    return {
        "newest": (Article.published_at.desc().nullslast(), Article.id.desc()),
        "oldest": (Article.published_at.asc().nullslast(), Article.id.asc()),
        "sentiment_high": (Article.sentiment.desc(), Article.id.desc()),
        "sentiment_low": (Article.sentiment.asc(), Article.id.desc()),
        "info": (Article.info_score.desc().nullslast(), Article.id.desc()),
    }[order]


def _ts(dt: datetime | None) -> float:
    """Timestamp of a datetime as epoch seconds, treating naive values as UTC."""
    if dt is None:
        return 0.0
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()


def report_rank(a: Article) -> tuple[float, int, float]:
    """Sort key for the reports of one story (use reverse=True): best score,
    then longer text, then newer."""
    return (a.info_score or 0.0, len(a.full_text or ""), _ts(a.published_at))


def ranked(members: list[Article]) -> list[Article]:
    """Reports sorted best first."""
    return sorted(members, key=report_rank, reverse=True)


def snippet(a: Article, limit: int = 220) -> str | None:
    """A short teaser from an article's summary."""
    text = (a.summary_deep or a.summary or "").strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def brief(a: Article) -> dict:
    """The compact form of a report shown under its story's lead."""
    return {
        "id": a.id, "title": a.title, "source": a.source, "url": a.url,
        "published_at": a.published_at, "sentiment": a.sentiment,
        "info_score": a.info_score, "summary": snippet(a), "image_url": a.image_url,
    }


def build_page(db: Session, ordered_ids: list[int], offset: int, limit: int) -> dict:
    """Group `ordered_ids` (already filtered and ordered) into stories and return one page.

    A story's position is where its first report appears in the requested order,
    so "newest" sorts stories by their newest report and "info" by their best.
    """
    by_article, _ = story_index.get_clusters(db)
    groups: dict[str, list[int]] = {}
    for article_id in ordered_ids:
        groups.setdefault(story_index.story_key(by_article.get(article_id), article_id), []).append(article_id)

    keys = list(groups)
    page_keys = keys[offset: offset + limit]
    page_ids = [i for k in page_keys for i in groups[k]]
    articles = {a.id: a for a in db.execute(select(Article).where(Article.id.in_(page_ids or [0]))).scalars()}

    active_watches = watches.active(db)
    stories = []
    leads = []
    for key in page_keys:
        members = ranked([articles[i] for i in groups[key] if i in articles])
        if not members:
            continue
        parsed = story_index.parse_story_key(key)
        lead = members[0]
        leads.append(lead)
        sources = list(dict.fromkeys(m.source for m in members))
        stories.append({
            "key": key,
            "cluster_id": parsed.id if parsed.is_cluster else None,
            "lead": lead,
            "others": [brief(m) for m in members[1:]],
            "report_count": len(members),
            "outlets": len(sources),
            "sources": sources,
            "best_score": lead.info_score,
            "watch_matches": watches.matching_terms(active_watches, members) if active_watches else [],
        })
    story_index.annotate(db, leads)
    return {"stories": stories, "total": len(keys), "article_total": len(ordered_ids)}


def count_matching(db: Session, q: Select) -> int:
    """Count the rows a query matches."""
    return db.scalar(select(func.count()).select_from(q.subquery())) or 0


def outlet_stats(members: list[Article]) -> list[dict]:
    """One row per outlet (its best report): information, wording, depth and who was first.

    Badges are relative to the other outlets of the same story."""
    best: dict[str, Article] = {}
    for m in ranked(members):
        best.setdefault(m.source, m)
    rows = []
    for m in best.values():
        sections = _sections(m.summary_structured)
        rows.append({
            "source": m.source, "report_id": m.id, "title": m.title, "info_score": m.info_score,
            "sentiment": m.sentiment, "chars": len(m.full_text or ""),
            "numbers": len(sections.get("By the numbers", [])), "quotes": len(sections.get("Notable quotes", [])),
            "published_at": m.published_at, "badges": [],
        })
    if len(rows) > 1:
        dated = [r for r in rows if r["published_at"]]
        if dated:
            min(dated, key=lambda r: _ts(r["published_at"]))["badges"].append("First to report")
        for metric, badge in (("chars", "Most detailed"), ("numbers", "Most figures"), ("quotes", "Most quotes")):
            top = max(rows, key=lambda r: r[metric])
            if top[metric]:
                top["badges"].append(badge)
    return sorted(rows, key=lambda r: (r["info_score"] or 0.0), reverse=True)


def story_detail(db: Session, cluster: Cluster, force_brief: bool = False) -> dict:
    """Build the detail view of one story from its member articles."""
    members = ranked(list(db.execute(select(Article).where(Article.id.in_(cluster.article_ids))).scalars()))
    sentiments = [m.sentiment for m in members]
    avg = sum(sentiments) / len(sentiments) if sentiments else 0.0
    comparison = outlet_stats(members)
    profiles = reliability.profiles(db)
    for row in comparison:  # how each outlet publishes, shown next to how it covered this story
        profile = profiles.get(row["source"])
        row["reliability"] = profile["score"] if profile else None
        row["reliability_label"] = profile["label"] if profile else None
    return {
        "cluster_id": cluster.id,
        "title": cluster.title,
        "report_count": len(members),
        "outlets": len({m.source for m in members}),
        "avg_sentiment": round(avg, 3),
        "sentiment_spread": round(max(sentiments) - min(sentiments), 3) if sentiments else 0.0,
        "reports": [brief(m) for m in members],
        "comparison": comparison,
        "brief": briefs.get_brief(db, cluster.id, cluster.title, members, force=force_brief),
        "claims": claims.get_claims(db, cluster.id, cluster.title, members, force=force_brief),
    }
