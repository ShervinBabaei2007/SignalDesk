"""Sample ("Demo") articles belong to the demo tour; workspaces and the owner see real articles."""

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
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import config, seed_data, story_index, workspace  # noqa: E402
from app.database import Base, SessionLocal, engine as app_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Article  # noqa: E402

NOW = datetime.now(timezone.utc)
client = TestClient(app)


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #

def test_sample_articles_are_dated_in_the_past():
    for marker in ("-2d", "-5h", "-30m"):
        assert seed_data._relative_published(marker) < datetime.now(timezone.utc)
    assert abs(seed_data._relative_published("-2d") - (datetime.now(timezone.utc) - timedelta(days=2))) < timedelta(seconds=5)


@pytest.fixture()
def db():
    """In-memory database."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as session:
        yield session


def article(i, *, seed, published, created=None, **kw):
    """One article."""
    fields = dict(id=i, title=f"Marker story {i}", url=f"https://x.test/{i}", source="S", topic="World", sentiment=0.0,
                  is_seed=seed, published_at=published, ingested_at=created or NOW)
    fields.update(kw)
    return Article(**fields)


def test_future_dated_sample_articles_are_moved_back_and_real_ones_are_left_alone(db):
    created = NOW - timedelta(hours=3)
    db.add_all([
        article(1, seed=True, published=created + timedelta(days=2), created=created),   # "-2d" turned into +2 days
        article(2, seed=True, published=created - timedelta(days=1), created=created),   # already fine
        article(3, seed=False, published=NOW + timedelta(hours=9), created=created),     # a real article is never touched here
    ])
    db.commit()
    assert seed_data.repair_seed_dates(db) == 1
    fixed = db.get(Article, 1).published_at.replace(tzinfo=timezone.utc)
    assert fixed == (created - timedelta(days=2)).replace(microsecond=fixed.microsecond) or abs(fixed - (created - timedelta(days=2))) < timedelta(seconds=1)
    assert db.get(Article, 2).published_at.replace(tzinfo=timezone.utc) == created - timedelta(days=1)
    assert db.get(Article, 3).published_at.replace(tzinfo=timezone.utc) > NOW
    assert seed_data.repair_seed_dates(db) == 0  # safe to run on every boot


# --------------------------------------------------------------------------- #
# Who sees the sample articles
# --------------------------------------------------------------------------- #

@pytest.fixture()
def marked(monkeypatch):
    """One sample and one real article with searchable titles; modes switched on."""
    monkeypatch.setattr(config, "API_TOKEN", "owner-secret")
    monkeypatch.setattr(config, "SESSION_SECRET", "owner-secret")
    monkeypatch.setattr(config, "DEMO_MODE", True)
    monkeypatch.setattr(workspace, "creations", workspace.RateLimiter(1000))
    Base.metadata.create_all(bind=app_engine)
    recent = NOW - timedelta(hours=1)
    with SessionLocal() as session:
        session.add_all([
            Article(id=88001, title="Zzmarker placeholder sample story", url="https://demo.signaldesk.local/zz1", source="SciScope",
                    topic="World", sentiment=0.0, is_seed=True, published_at=recent),
            Article(id=88002, title="Zzmarker genuine reported story", url="https://news.example/zz2", source="BBC World",
                    topic="World", sentiment=0.0, is_seed=False, published_at=recent),
        ])
        session.commit()
    story_index.reset_cache()
    yield
    with SessionLocal() as session:
        session.query(Article).filter(Article.id.in_([88001, 88002])).delete()
        session.commit()
    story_index.reset_cache()


def titles(headers=None, path="/api/articles?search=Zzmarker&limit=50"):
    """Titles returned for the marker search."""
    res = client.get(path, headers=headers or {})
    assert res.status_code == 200
    return {a["title"] for a in res.json()["items"]}


SAMPLE, REAL = "Zzmarker placeholder sample story", "Zzmarker genuine reported story"


def test_plain_browsing_and_the_demo_tour_still_show_the_sample_articles(marked):
    assert titles() == {SAMPLE, REAL}
    demo = client.post("/api/demo/session").json()["token"]
    assert titles({"X-API-Key": demo}) == {SAMPLE, REAL}


def test_a_workspace_shows_real_articles_only(marked):
    token = client.post("/api/workspace").json()["token"]
    assert titles({"X-API-Key": token}) == {REAL}


def test_the_owner_sees_real_articles_only(marked):
    assert titles({"X-API-Key": "owner-secret"}) == {REAL}


def test_a_wrong_token_is_not_the_owner_and_still_sees_the_demo_content(marked):
    assert titles({"X-API-Key": "not-the-owner-token"}) == {SAMPLE, REAL}


def test_the_grouped_feed_and_the_counts_follow_the_same_rule(marked):
    token = {"X-API-Key": client.post("/api/workspace").json()["token"]}
    anon_total = client.get("/api/stats").json()["total_articles"]
    with SessionLocal() as session:  # other test modules seed the shared test database too, so count the samples
        samples = session.query(Article).filter(Article.is_seed.is_(True)).count()
    assert samples >= 1
    assert client.get("/api/stats", headers=token).json()["total_articles"] == anon_total - samples
    stories = client.get("/api/stories?search=Zzmarker&limit=50", headers=token).json()["items"]
    assert {s["lead"]["title"] for s in stories} == {REAL}
    assert not any(s["lead"]["is_seed"] for s in client.get("/api/stories?limit=100", headers=token).json()["items"])


def test_a_workspace_can_still_open_a_real_article_but_not_a_sample_one_by_id(marked):
    token = {"X-API-Key": client.post("/api/workspace").json()["token"]}
    assert client.get("/api/articles/88002", headers=token).status_code == 200
    assert client.get("/api/articles/88001", headers=token).status_code == 404
    assert client.get("/api/articles/88001").status_code == 200  # the demo tour can
