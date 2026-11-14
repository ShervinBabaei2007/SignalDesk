"""Claim-level comparison: agreed, disputed and single-source claims."""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_test_dir = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_test_dir}/test.db")
os.environ["INGEST_INTERVAL_MINUTES"] = "0"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import briefs, claims, llm, story_index  # noqa: E402
from app.database import Base, SessionLocal, engine as app_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Article, StoryBrief  # noqa: E402

NOW = datetime.now(timezone.utc)

BBC = ("The central bank raised interest rates by 0.5 percent on Wednesday, officials said. "
       "Inflation reached 4.2 percent in March according to the statistics office. "
       "The finance ministry announced a $4.2 billion relief package for farmers this week. "
       "Analysts described the decision as widely expected by the markets.")
REUTERS = ("Officials said the central bank raised interest rates by 0.5 percent on Wednesday. "
           "Inflation was 5.1 percent in March, according to the statistics office. "
           "Shares in the banking sector rose sharply after the announcement was made.")


def article(i, source, text, **kw):
    """An article with extracted text."""
    fields = dict(id=i, title="Central bank raises rates as inflation bites", url=f"https://x.test/{i}",
                  source=source, topic="Business", sentiment=0.0, full_text=text, is_seed=False,
                  published_at=NOW - timedelta(hours=i))
    fields.update(kw)
    return Article(**fields)


def by_text(items, needle):
    """The claim containing `needle`."""
    return next(c for c in items if needle in c["text"])


# --------------------------------------------------------------------------- #
# Extractive comparison
# --------------------------------------------------------------------------- #

def test_claims_are_agreed_disputed_or_single_source():
    items = claims.extractive_claims("t", [article(1, "BBC", BBC), article(2, "Reuters", REUTERS)])
    rate = by_text(items, "interest rates")
    assert rate["status"] == "agreed" and set(rate["outlets"]) == {"BBC", "Reuters"} and rate["values"] is None
    inflation = by_text(items, "Inflation")
    assert inflation["status"] == "disputed"
    assert inflation["values"] == {"BBC": "4.2 percent", "Reuters": "5.1 percent"}
    relief = by_text(items, "relief package")
    assert relief["status"] == "single" and relief["outlets"] == ["BBC"]
    assert [c["status"] for c in items] == sorted((c["status"] for c in items), key=["disputed", "agreed", "single"].index)


def test_a_sentence_only_one_outlet_makes_and_that_has_no_figure_is_not_shown():
    items = claims.extractive_claims("t", [article(1, "BBC", BBC), article(2, "Reuters", REUTERS)])
    assert not any("Analysts described" in c["text"] for c in items)
    assert not any("Shares in the banking" in c["text"] for c in items)


def test_figures_within_tolerance_are_the_same_figure():
    close = claims.extractive_claims("t", [
        article(1, "A", "Inflation reached 4.20 percent in March according to the statistics office."),
        article(2, "B", "Inflation reached 4.21 percent in March according to the statistics office.")])
    assert close[0]["status"] == "agreed"


def test_different_kinds_of_figure_are_not_a_conflict():
    items = claims.extractive_claims("t", [
        article(1, "A", "The ministry announced a relief package for farmers worth 4.2 percent of the annual budget."),
        article(2, "B", "The ministry announced a relief package for farmers worth $4.2 billion in new spending.")])
    assert items and items[0]["status"] == "agreed"


def test_magnitude_words_are_understood():
    assert claims.figure_value("$4.2 billion") == ("money", 4.2e9)
    assert claims.figure_value("4,200 million") == ("num", 4.2e9)
    assert claims.figure_value("12%") == ("pct", 12.0)
    assert claims.figure_value("no number") is None


def test_page_furniture_and_video_timestamps_are_not_claims():
    for junk in ("In this article MSFT watch now VIDEO 2:03 02:03 Widespread Microsoft outage stretches into second day",
                 "Subscribe to our newsletter to read more about the 2:03 clip from the Federal Reserve announcement",
                 "The clip runs for 2:03 and was filmed by the local broadcaster on the day"):
        assert not claims.is_checkable(junk), junk
    assert claims.is_checkable("The central bank raised rates by 0.5 percent on Wednesday, officials said.")


def test_one_outlet_alone_has_no_agreement_and_nothing_crashes_on_empty_reports():
    solo = claims.extractive_claims("t", [article(1, "BBC", BBC)])
    assert all(c["status"] == "single" for c in solo) and len(solo) <= claims.MAX_SINGLE
    assert claims.extractive_claims("t", []) == []
    assert claims.extractive_claims("t", [article(1, "BBC", "")]) == []


# --------------------------------------------------------------------------- #
# Model output and the LLM / fallback choice
# --------------------------------------------------------------------------- #

def test_model_claims_are_validated():
    raw = {"claims": [
        {"text": "Rates rose 0.5 percent.", "status": "agreed", "outlets": ["BBC", "Reuters", "Ghost"]},
        {"text": "Inflation figure differs.", "status": "disputed", "outlets": ["BBC", "Reuters"],
         "values": {"BBC": "4.2 percent", "Reuters": "5.1 percent", "Ghost": "9"}},
        {"text": "Only one value given.", "status": "disputed", "outlets": ["BBC"], "values": {"BBC": "1"}},
        {"text": "Bad status.", "status": "maybe", "outlets": ["BBC"]},
        {"text": "", "status": "agreed", "outlets": ["BBC"]},
        {"text": "Unknown outlets only.", "status": "agreed", "outlets": ["Ghost"]},
        "junk",
    ]}
    items = claims.normalize_claims(raw, {"BBC", "Reuters"})
    assert [c["text"] for c in items] == ["Rates rose 0.5 percent.", "Inflation figure differs.", "Only one value given."]
    assert items[0]["outlets"] == ["BBC", "Reuters"]
    assert items[1]["values"] == {"BBC": "4.2 percent", "Reuters": "5.1 percent"}
    assert items[2]["values"] is None
    assert claims.normalize_claims({"claims": "nope"}, {"BBC"}) is None
    assert claims.normalize_claims({"claims": []}, {"BBC"}) is None
    assert claims.normalize_claims("nope", {"BBC"}) is None


MEMBERS = [article(1, "BBC", BBC), article(2, "Reuters", REUTERS)]
GOOD = {"claims": [{"text": "Rates rose 0.5 percent.", "status": "agreed", "outlets": ["BBC", "Reuters"]}]}


def test_the_model_is_used_when_available_and_the_fallback_when_it_fails(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "story_claims", lambda **kw: GOOD)
    assert claims.build_claims("t", MEMBERS) == {"kind": "ai", "items": claims.normalize_claims(GOOD, {"BBC", "Reuters"})}
    monkeypatch.setattr(llm, "story_claims", lambda **kw: {"claims": "garbage"})
    assert claims.build_claims("t", MEMBERS)["kind"] == "auto"
    monkeypatch.setattr(llm, "story_claims", lambda **kw: None)
    assert claims.build_claims("t", MEMBERS)["kind"] == "auto"
    monkeypatch.setattr(llm, "available", lambda: False)
    assert claims.build_claims("t", MEMBERS)["kind"] == "auto"


def test_a_visitors_articles_never_reach_the_model(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "story_claims", lambda **kw: pytest.fail("must not spend the owner's quota"))
    monkeypatch.setattr(llm, "story_brief", lambda **kw: pytest.fail("must not spend the owner's quota"))
    mine = [article(1, "BBC", BBC, workspace_id="visitor"), article(2, "Reuters", REUTERS)]
    assert claims.build_claims("t", mine)["kind"] == "auto"
    assert briefs.build_brief("t", mine)["kind"] == "auto"


# --------------------------------------------------------------------------- #
# Caching with the brief
# --------------------------------------------------------------------------- #

@pytest.fixture()
def db():
    """In-memory database."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as session:
        session.add_all([article(1, "BBC", BBC), article(2, "Reuters", REUTERS)])
        session.commit()
        yield session


def test_claims_are_cached_on_the_brief_row_and_rebuilt_when_the_story_changes(db, monkeypatch):
    members = db.query(Article).order_by(Article.id).all()
    briefs.get_brief(db, 1, "t", members)  # creates the row the claims live on
    built = []
    real = claims.build_claims
    monkeypatch.setattr(claims, "build_claims", lambda t, m: (built.append(1), real(t, m))[1])
    first = claims.get_claims(db, 1, "t", members)
    assert claims.get_claims(db, 1, "t", members) == first and len(built) == 1  # served from the cache
    assert json.loads(db.get(StoryBrief, 1).claims) == first
    claims.get_claims(db, 1, "t", members, force=True)
    assert len(built) == 2  # a forced refresh rebuilds
    # a new report changes the fingerprint: the brief is rewritten and the stale claims are cleared
    db.add(article(3, "AP", "Officials said the central bank raised interest rates by 0.5 percent on Wednesday."))
    db.commit()
    bigger = db.query(Article).order_by(Article.id).all()
    briefs.get_brief(db, 1, "t", bigger)
    assert db.get(StoryBrief, 1).claims is None
    claims.get_claims(db, 1, "t", bigger)
    assert len(built) == 3


def test_a_corrupt_cache_is_rebuilt_not_a_crash(db):
    members = db.query(Article).order_by(Article.id).all()
    briefs.get_brief(db, 1, "t", members)
    db.get(StoryBrief, 1).claims = "{not json"
    db.commit()
    assert claims.get_claims(db, 1, "t", members)["kind"] == "auto"


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #

def test_the_story_endpoint_returns_the_claims():
    Base.metadata.create_all(bind=app_engine)
    with SessionLocal() as session:
        recent = NOW - timedelta(hours=1)
        session.add_all([article(9001, "BBC", BBC, published_at=recent), article(9002, "Reuters", REUTERS, published_at=recent)])
        session.commit()
    story_index.reset_cache()
    try:
        client = TestClient(app)
        res = client.get("/api/stories/9001")
        assert res.status_code == 200
        body = res.json()["claims"]
        assert body["kind"] == "auto"
        statuses = {c["status"] for c in body["items"]}
        assert {"agreed", "disputed"} <= statuses
        disputed = next(c for c in body["items"] if c["status"] == "disputed")
        assert disputed["values"] == {"BBC": "4.2 percent", "Reuters": "5.1 percent"}
    finally:
        with SessionLocal() as session:
            session.query(StoryBrief).filter(StoryBrief.cluster_id == 9001).delete()
            session.query(Article).filter(Article.id.in_([9001, 9002])).delete()
            session.commit()
        story_index.reset_cache()
