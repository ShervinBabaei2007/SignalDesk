"""Sentiment classification: one threshold, everywhere it is used."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import reporting, sentiment, stories  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import Article  # noqa: E402

BOUNDARY_SCORES = [-1.0, -0.151, -0.15, -0.149, 0.0, 0.149, 0.15, 0.151, 1.0]


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as session:
        now = datetime.now(timezone.utc)
        for i, score in enumerate(BOUNDARY_SCORES):
            session.add(Article(title=f"Story {i}", url=f"https://t.example/{i}", source="Wire",
                                topic="World", sentiment=score,
                                published_at=now - timedelta(minutes=i), is_seed=False))
        session.commit()
        yield session


@pytest.mark.parametrize("score,expected", [
    (-1.0, "negative"), (-0.151, "negative"), (-0.15, "neutral"), (0.0, "neutral"),
    (0.15, "neutral"), (0.151, "positive"), (1.0, "positive"),
])
def test_label_boundaries(score, expected):
    assert sentiment.label(score) == expected


def test_counts_always_has_all_three_labels():
    assert sentiment.counts([]) == {"positive": 0, "neutral": 0, "negative": 0}
    assert sentiment.counts([0.5, 0.0, -0.5, 0.9]) == {"positive": 2, "neutral": 1, "negative": 1}


def test_tone_follows_the_same_thresholds():
    assert "positive" in sentiment.tone(0.2)
    assert "negative" in sentiment.tone(-0.2)
    assert "mix" in sentiment.tone(0.15)


def test_sql_filter_agrees_with_label_for_every_boundary_score(db):
    for wanted in sentiment.LABELS:
        q = select(Article.sentiment).where(*sentiment.conditions(Article.sentiment, wanted))
        selected = sorted(s for (s,) in db.execute(q))
        expected = sorted(s for s in BOUNDARY_SCORES if sentiment.label(s) == wanted)
        assert selected == expected


def test_feed_filter_stats_and_label_property_agree(db):
    by_label = sentiment.counts(BOUNDARY_SCORES)
    result = reporting.stats(db)
    assert (result.positive, result.neutral, result.negative) == (
        by_label["positive"], by_label["neutral"], by_label["negative"])
    for wanted in sentiment.LABELS:
        q = stories.apply_filters(db, select(Article), search=None, source=None, topic=None,
                                  sentiment=wanted, cluster=None, hot=False, ids=None)
        rows = db.execute(q).scalars().all()
        assert len(rows) == by_label[wanted]
        assert {a.sentiment_label for a in rows} == {wanted}


def test_digest_top_items_use_the_same_thresholds(db):
    digest = reporting.digest(db)
    assert all(sentiment.label(i.sentiment) == "positive" for i in digest.top_positive)
    assert all(sentiment.label(i.sentiment) == "negative" for i in digest.top_negative)
    assert 0.15 not in {i.sentiment for i in digest.top_positive}
