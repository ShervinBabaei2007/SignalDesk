"""Historical event tracking: durable events and day-by-day timelines."""

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

from app import events, pipeline, story_index  # noqa: E402
from app.database import Base, SessionLocal, engine as app_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Article, Event, EventArticle, Feed  # noqa: E402

NOW = datetime.now(timezone.utc)
FLOOD = "Hurricane Maria floods coastal towns as thousands evacuate"
VOTE = "Parliament passes sweeping budget bill after marathon debate"


@pytest.fixture()
def db():
    """In-memory database; the story cache is cleared around each test."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    story_index.reset_cache()
    with sessionmaker(bind=engine)() as session:
        yield session
    story_index.reset_cache()


def add(db, i, title=FLOOD, source=None, age_hours=1.0, sentiment=0.0, **kw):
    """Add one report of a story, published `age_hours` ago."""
    fields = dict(id=i, title=title, url=f"https://x.test/{i}", source=source or f"Src{i}", topic="World",
                  sentiment=sentiment, is_seed=False, published_at=NOW - timedelta(hours=age_hours))
    fields.update(kw)
    db.add(Article(**fields))


def refresh(db):
    """Commit, drop the story cache and assign events."""
    db.commit()
    story_index.reset_cache()
    return events.assign(db)


def event_count(db):
    """How many events exist."""
    return len(db.execute(select(Event)).scalars().all())


# --------------------------------------------------------------------------- #
# Assigning events
# --------------------------------------------------------------------------- #

def test_each_story_becomes_one_event_and_assigning_again_changes_nothing(db):
    for i, title in enumerate([FLOOD, FLOOD, VOTE, VOTE], start=1):
        add(db, i, title=title, age_hours=i)
    assert refresh(db) == 2
    assert event_count(db) == 2
    rows = db.execute(select(EventArticle)).scalars().all()
    assert len(rows) == 4
    before = sorted((r.article_id, r.event_id) for r in rows)
    refresh(db)
    assert event_count(db) == 2 and sorted((r.article_id, r.event_id) for r in db.execute(select(EventArticle)).scalars()) == before


def test_new_reports_extend_the_event_instead_of_creating_another(db):
    add(db, 1, age_hours=5)
    add(db, 2, age_hours=4)
    refresh(db)
    event = db.execute(select(Event)).scalar_one()
    first_seen, peak = event.first_seen, event.peak_reports
    add(db, 3, age_hours=1)
    refresh(db)
    event = db.execute(select(Event)).scalar_one()
    assert event.first_seen == first_seen and event.peak_reports == peak + 1
    assert len(db.execute(select(EventArticle)).scalars().all()) == 3


def test_an_event_keeps_its_history_after_the_story_id_changes(db):
    """The cluster id is the smallest article id in the window; when the oldest report ages out it changes."""
    add(db, 1, age_hours=70)   # about 2.9 days old: still inside the 3-day window
    add(db, 2, age_hours=40)  # reports of one story must be within 48h of each other to be linked
    refresh(db)
    _, by_id = story_index.get_clusters(db)
    assert set(by_id) == {1}
    event_id = db.execute(select(Event.id)).scalar_one()

    db.get(Article, 1).published_at = NOW - timedelta(hours=100)  # now outside the window
    add(db, 3, age_hours=2)
    add(db, 4, age_hours=1)
    refresh(db)
    _, by_id = story_index.get_clusters(db)
    assert set(by_id) == {2}  # a different story id for the same story
    assert event_count(db) == 1 and db.execute(select(Event.id)).scalar_one() == event_id
    tl = events.timeline(db, by_id[2])
    assert tl["reports"] == 4 and tl["event_id"] == event_id  # report 1 is outside the window but still counted


def test_events_that_turn_out_to_be_one_story_are_merged(db):
    for i in range(1, 5):
        add(db, i, age_hours=i)
    db.commit()
    for event_id, members in ((1, (1, 2)), (2, (3, 4))):  # as if they had been tracked as two events
        db.add(Event(id=event_id, title=FLOOD, first_seen=NOW - timedelta(hours=9), last_seen=NOW, peak_reports=2))
        db.add_all([EventArticle(article_id=a, event_id=event_id) for a in members])
    db.commit()
    story_index.reset_cache()
    events.assign(db)
    assert [e.id for e in db.execute(select(Event)).scalars()] == [1]
    assert {r.event_id for r in db.execute(select(EventArticle)).scalars()} == {1}
    assert len(db.execute(select(EventArticle)).scalars().all()) == 4


def test_a_visitor_session_never_writes_events(db):
    add(db, 1)
    add(db, 2)
    db.info["workspace"] = "visitor"
    db.commit()
    story_index.reset_cache()
    assert events.assign(db) == 0 and event_count(db) == 0


# --------------------------------------------------------------------------- #
# Timelines
# --------------------------------------------------------------------------- #

def test_timeline_buckets_by_day_fills_gaps_and_tracks_who_joined_and_the_tone(db):
    add(db, 1, source="BBC", age_hours=60, sentiment=-0.6)    # day 1
    add(db, 2, source="Reuters", age_hours=59, sentiment=-0.4)
    add(db, 3, source="BBC", age_hours=11, sentiment=-0.1)    # day 3 (a quiet day 2 between)
    add(db, 4, source="AP", age_hours=10, sentiment=0.1)
    refresh(db)
    _, by_id = story_index.get_clusters(db)
    tl = events.timeline(db, by_id[1])
    first_day = (NOW - timedelta(hours=60)).date()
    assert tl["reports"] == 4 and tl["outlets"] == 3 and tl["first_reported_by"] == "BBC"
    dates = [d["date"] for d in tl["days"]]
    assert dates == sorted(dates) and dates[0] == first_day.isoformat() and len(dates) == tl["days_active"]
    assert dates == [(first_day + timedelta(days=n)).isoformat() for n in range(len(dates))]  # no missing days
    assert sum(d["reports"] for d in tl["days"]) == 4
    quiet = [d for d in tl["days"] if d["reports"] == 0]
    assert all(d["avg_sentiment"] is None and d["new_outlets"] == [] for d in quiet)
    joined = [o for d in tl["days"] for o in d["new_outlets"]]
    assert joined == ["BBC", "Reuters", "AP"]  # each outlet is "new" on exactly one day, in order
    assert tl["sentiment_shift"] == pytest.approx(0.5)  # day 1 averaged -0.5, the last day 0.0
    assert tl["days"][0]["headline"] == FLOOD


def test_a_workspace_timeline_is_computed_from_its_own_story_without_events(db):
    add(db, 1, source="Mine", workspace_id="visitor", age_hours=3)
    add(db, 2, source="Other", age_hours=2)
    db.commit()
    db.info["workspace"] = "visitor"
    story_index.reset_cache()
    _, by_id = story_index.get_clusters(db)
    tl = events.timeline(db, by_id[1])
    assert tl["event_id"] is None and tl["reports"] == 2 and event_count(db) == 0


def test_timeline_of_a_single_day_story(db):
    add(db, 1, age_hours=3)
    add(db, 2, age_hours=2)
    refresh(db)
    _, by_id = story_index.get_clusters(db)
    tl = events.timeline(db, by_id[1])
    assert tl["days_active"] in (1, 2) and tl["sentiment_shift"] == 0.0


# --------------------------------------------------------------------------- #
# Wiring: the pipeline and the API
# --------------------------------------------------------------------------- #

def test_an_ingest_cycle_keeps_events_in_step(db, monkeypatch):
    add(db, 1, age_hours=2)
    add(db, 2, age_hours=1)
    db.add(Feed(name="BBC", url="https://bbc.example/rss", is_active=True))
    db.commit()
    story_index.reset_cache()
    monkeypatch.setattr(pipeline, "_last_finished", 0.0)
    pipeline.ingest_cycle(db, manual=False, ingest=lambda s, feeds, feed_rows=None: [])
    assert event_count(db) == 1


def test_the_timeline_and_trending_endpoints_expose_events():
    Base.metadata.create_all(bind=app_engine)
    recent = NOW - timedelta(hours=1)
    with SessionLocal() as session:
        for i, source in ((9101, "BBC"), (9102, "Reuters")):
            session.add(Article(id=i, title=FLOOD, url=f"https://x.test/{i}", source=source, topic="World",
                                sentiment=0.0, is_seed=False, published_at=recent))
        session.commit()
        story_index.reset_cache()
        events.assign(session)
    try:
        client = TestClient(app)
        tl = client.get("/api/stories/9101/timeline")
        assert tl.status_code == 200
        body = tl.json()
        assert body["reports"] == 2 and body["outlets"] == 2 and body["event_id"] and body["days"]
        hot = [s for s in client.get("/api/trending").json() if s["cluster_id"] == 9101]
        assert hot and hot[0]["first_seen"] and hot[0]["days_active"] >= 1
        assert client.get("/api/stories/999999/timeline").status_code == 404
    finally:
        with SessionLocal() as session:
            session.execute(EventArticle.__table__.delete().where(EventArticle.article_id.in_([9101, 9102])))
            session.execute(Event.__table__.delete())
            session.execute(Article.__table__.delete().where(Article.id.in_([9101, 9102])))
            session.commit()
        story_index.reset_cache()
