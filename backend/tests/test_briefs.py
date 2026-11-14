"""Story briefs and the story detail endpoint."""

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

_test_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_dir}/briefs.db"
os.environ["INGEST_INTERVAL_MINUTES"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import briefs, clustering, llm  # noqa: E402
from app.briefs import extractive_brief, figures, member_hash  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Article  # noqa: E402

NOW = datetime.now(timezone.utc)
client = TestClient(app)


def report(i, source, sentiment, sentences, structured=None):
    return SimpleNamespace(id=i, source=source, sentiment=sentiment, title=f"Report {i}", summary=None,
                           summary_deep=sentences[0], summary_structured=structured, full_text=" ".join(sentences))


# --- extractive writer ---------------------------------------------------------

LEAD = report(1, "Alpha", -0.2, [
    "The outage grounded about 1,200 flights across the country on Friday afternoon, officials said.",
    "Engineers worked through the night to restore the communications system for air traffic controllers.",
    "The agency said it expects normal operations to resume by Saturday morning at the latest.",
], structured="## Key points\n- The outage grounded about 1,200 flights across the country on Friday afternoon, officials said.\n"
              "- Engineers worked through the night to restore the communications system for air traffic controllers.")
SECOND = report(2, "Beta", -0.1, [
    "Around 1,200 flights were grounded across the country on Friday as the outage spread, the agency said.",
    "Airlines estimate the disruption cost them roughly $400 million in lost revenue and compensation.",
])
THIRD = report(3, "Gamma", -0.9, [
    "A catastrophic failure left travellers stranded as engineers scrambled to restore the control system.",
    "Passengers described chaos at major airports while the communications system stayed offline.",
])


def test_figures_ignore_years_times_and_tiny_numbers():
    found = figures("In 2026 at 9 pm about 1,200 flights and $400 million, or 35% of 12 routes, were hit.")
    assert set(found) == {"1200", "$400million", "35%"}


def test_extractive_brief_finds_shared_figures_and_corroborated_points():
    brief = extractive_brief("Outage grounds flights", [LEAD, SECOND, THIRD])
    assert brief["kind"] == "auto" and brief["model"] is None
    text = " ".join(brief["agree"])
    assert "1,200 flights" in text and "2 outlets cite 1,200" in text
    assert 1 <= len(brief["agree"]) <= 4


def test_extractive_brief_flags_outlier_wording_and_single_outlet_figures():
    brief = extractive_brief("Outage grounds flights", [LEAD, SECOND, THIRD])
    differ = " ".join(brief["differ"])
    assert "Gamma uses noticeably more negative wording" in differ
    assert "Only Beta cites $400 million" in differ


def test_extractive_brief_is_deterministic_and_handles_a_single_outlet():
    first = extractive_brief("T", [LEAD, SECOND, THIRD])
    assert first == extractive_brief("T", [LEAD, SECOND, THIRD])
    alone = extractive_brief("T", [LEAD])
    assert alone["differ"] == ["Only one outlet has covered this so far."]
    assert alone["agree"]  # never empty


def test_member_hash_changes_with_members_but_not_order():
    assert member_hash([3, 1, 2]) == member_hash([1, 2, 3])
    assert member_hash([1, 2]) != member_hash([1, 2, 3])


# --- language-model path -------------------------------------------------------

def test_story_brief_normalisation_accepts_good_json_and_rejects_empty():
    ok = llm.normalize_story_brief({"headline": " Flights grounded ", "agree": ["a", "b"], "differ": ["c"]})
    assert ok == {"headline": "Flights grounded", "agree": ["a", "b"], "differ": ["c"]}
    assert llm.normalize_story_brief({"headline": "x", "agree": []}) is None
    assert llm.normalize_story_brief({"agree": "not a list"}) is None


def test_llm_story_brief_end_to_end_with_a_stubbed_model(monkeypatch):
    provider = SimpleNamespace(model="stub-1")
    monkeypatch.setattr(llm, "get_provider", lambda: provider)
    monkeypatch.setattr(llm, "_complete_json",
                        lambda p, system, user: '```json\n{"headline": "H", "agree": ["one shared fact"], "differ": []}\n```')
    result = llm.story_brief(title="T", reports=[{"source": "A", "title": "t", "text": "body", "sentiment": 0.0}])
    assert result == {"headline": "H", "agree": ["one shared fact"], "differ": [], "model": "stub-1"}
    monkeypatch.setattr(llm, "_complete_json", lambda p, system, user: "sorry, I cannot")
    assert llm.story_brief(title="T", reports=[{"source": "A", "title": "t", "text": "b", "sentiment": 0.0}]) is None


def test_build_brief_prefers_the_model_and_falls_back_cleanly(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "story_brief",
                        lambda **k: {"headline": "AI headline", "agree": ["x"], "differ": [], "model": "m"})
    ai = briefs.build_brief("T", [LEAD, SECOND])
    assert ai["kind"] == "ai" and ai["headline"] == "AI headline" and ai["differ"]
    monkeypatch.setattr(llm, "story_brief", lambda **k: None)
    assert briefs.build_brief("T", [LEAD, SECOND])["kind"] == "auto"
    monkeypatch.setattr(llm, "available", lambda: False)
    assert briefs.build_brief("T", [LEAD, SECOND])["kind"] == "auto"


# --- endpoint, cache and comparison --------------------------------------------

def _add(db, i, source, title, score, chars, sentiment, structured=None, minutes=0):
    db.add(Article(title=title, url=f"https://b.example/{i}", source=source, topic="Science", sentiment=sentiment,
                   info_score=score, full_text="word " * chars, summary_structured=structured,
                   published_at=NOW - timedelta(minutes=minutes), is_seed=False))


@pytest.fixture(scope="module")
def comet_story():
    Base.metadata.create_all(bind=engine)
    numbers = "## By the numbers\n- The comet is 4,000 km wide.\n## Notable quotes\n- \"A rare sight,\" said one astronomer."
    with SessionLocal() as db:
        _add(db, 1, "Aout", "Giant comet becomes visible to naked eye over Europe tonight", 40.0, 300, -0.1, minutes=30)
        _add(db, 2, "Bout", "Comet giant visible to the naked eye over Europe tonight", 88.0, 1200, 0.1, numbers, minutes=10)
        _add(db, 3, "Cout", "Naked eye visible giant comet tonight over Europe skies", 60.0, 700, 0.0, minutes=20)
        db.commit()
    clustering._cache["key"] = None
    stories = client.get("/api/stories?limit=50").json()["items"]
    story = next(s for s in stories if "comet" in s["lead"]["title"].lower())
    return story["cluster_id"]


def test_story_detail_ranks_reports_and_compares_outlets(comet_story):
    res = client.get(f"/api/stories/{comet_story}")
    assert res.status_code == 200
    body = res.json()
    assert body["report_count"] == 3 and body["outlets"] == 3
    assert [r["source"] for r in body["reports"]] == ["Bout", "Cout", "Aout"]  # best-informed first
    comparison = {c["source"]: c for c in body["comparison"]}
    assert [c["source"] for c in body["comparison"]][0] == "Bout"
    assert "First to report" in comparison["Aout"]["badges"]  # oldest published
    assert "Most detailed" in comparison["Bout"]["badges"]  # longest text
    assert comparison["Bout"]["numbers"] == 1 and comparison["Bout"]["quotes"] == 1
    assert body["brief"]["kind"] == "auto" and body["brief"]["agree"]


def test_brief_is_cached_until_the_story_changes(comet_story, monkeypatch):
    calls = []
    real = briefs.build_brief
    monkeypatch.setattr(briefs, "build_brief", lambda t, m: (calls.append(1), real(t, m))[1])
    client.get(f"/api/stories/{comet_story}")
    client.get(f"/api/stories/{comet_story}")
    assert len(calls) <= 1  # at most one build for the pair; the second is served from the cache
    before = len(calls)
    client.get(f"/api/stories/{comet_story}")
    assert len(calls) == before  # still cached

    with SessionLocal() as db:  # a new report joins the story
        _add(db, 4, "Dout", "Giant comet visible to naked eye tonight over Europe sky watchers", 30.0, 200, 0.0, minutes=5)
        db.commit()
    clustering._cache["key"] = None
    detail = client.get(f"/api/stories/{comet_story}").json()
    assert detail["report_count"] == 4
    assert len(calls) == before + 1  # the changed story was re-briefed


def test_unknown_story_is_404(comet_story):
    assert client.get("/api/stories/999999").status_code == 404
    assert client.post("/api/stories/999999/brief").status_code == 404


def test_refresh_brief_requires_a_token_when_configured(comet_story, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "API_TOKEN", "s3cret")
    assert client.post(f"/api/stories/{comet_story}/brief").status_code == 401
    ok = client.post(f"/api/stories/{comet_story}/brief", headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200 and ok.json()["brief"]["agree"]
