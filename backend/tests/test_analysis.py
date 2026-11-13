"""Unit tests for the SignalDesk analysis engine."""

import os
import tempfile

# Any test here that touches the database must never use the developer's real one.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/analysis.db")

from app.analysis import analyze, classify_topic, extract_keywords, score_sentiment, summarize


def test_positive_sentiment():
    score = score_sentiment("Company reports record profits and strong growth")
    assert score > 0.3


def test_negative_sentiment():
    score = score_sentiment("Firm announces layoffs amid heavy losses and crisis fears")
    assert score < -0.3


def test_neutral_sentiment():
    score = score_sentiment("The board meeting is scheduled for Tuesday")
    assert -0.15 <= score <= 0.15


def test_sentiment_negation():
    plain = score_sentiment("profits are strong")
    negated = score_sentiment("profits are not strong")
    assert plain > negated
    # "not strong" should contribute negatively, pulling the mixed sentence down
    assert negated < 0.2


def test_sentiment_bounded():
    score = score_sentiment("very very very strong breakthrough record success win win win")
    assert -1.0 <= score <= 1.0


def test_topic_classification():
    assert classify_topic("New AI chip beats GPU benchmarks for data centers") == "Technology"
    assert classify_topic("Inflation and interest rate decisions worry investors") == "Business"
    assert classify_topic("NASA telescope discovers planet in distant space") == "Science"


def test_summarize_truncates():
    text = "Sentence one. " * 100
    summary = summarize(text)
    assert len(summary) <= 280


def test_keywords_exclude_stopwords():
    words = extract_keywords("the the the and the chip chip chip data data test")
    assert "the" not in words
    assert "and" not in words
    assert "chip" in words


def test_analyze_pipeline():
    result = analyze("Scientists discover breakthrough cancer treatment with strong results")
    assert set(result) == {"sentiment", "topic", "summary", "keywords"}
    assert result["topic"] == "Science"
    assert result["sentiment"] > 0


def test_ingest_decodes_html_entities_in_titles(monkeypatch):
    """Feeds that send &#8217; in titles must not leak raw entities into the UI."""
    from types import SimpleNamespace

    from app import ingestion
    from app.database import Base, SessionLocal, engine
    from app.models import Article

    Base.metadata.create_all(bind=engine)
    entry = SimpleNamespace(title="Microsoft&#8217;s outage &amp; fallout", link="https://x.example/entity-test",
                            summary="It&#8217;s big", published_parsed=None, updated_parsed=None)
    monkeypatch.setattr(ingestion.feedparser, "parse", lambda url: SimpleNamespace(entries=[entry]))
    with SessionLocal() as db:
        ingestion.ingest_feed(db, "https://feed.example/rss", "Test")
        art = db.query(Article).filter_by(url="https://x.example/entity-test").one()
        assert art.title == "Microsoft\u2019s outage & fallout"
