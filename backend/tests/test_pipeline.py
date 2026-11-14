"""The ingest cycle: one set of rules for the manual button and the scheduler."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import config, enrichment, pipeline  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import Article, Feed  # noqa: E402


@pytest.fixture()
def session_factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([Feed(name="Active", url="https://a.example/rss", is_active=True),
                    Feed(name="Paused", url="https://p.example/rss", is_active=False)])
        db.add(Article(title="Waiting", url="https://a.example/1", source="Active", topic="World",
                       sentiment=0.0, published_at=datetime.now(timezone.utc), is_seed=False))
        db.add(Article(title="Demo", url="https://a.example/2", source="Seed", topic="World",
                       sentiment=0.0, is_seed=True))
        db.commit()
    monkeypatch.setattr(pipeline, "_last_finished", 0.0)
    return factory


def fake_ingest(calls):
    def ingest(db, feeds, feed_rows=None):
        calls.append([f["name"] for f in feeds])
        return [{"feed": f["name"], "added": 2, "fetched": 3, "skipped": 1} for f in feeds]
    return ingest


def test_cycle_fetches_only_active_feeds_and_reports_what_is_waiting(session_factory):
    calls = []
    with session_factory() as db:
        result = pipeline.ingest_cycle(db, ingest=fake_ingest(calls))
    assert calls == [["Active"]]
    assert result.enrich_pending == 1          # the seed article never counts as pending
    assert result.enrich_needed is True
    assert result.alerts == []


def test_manual_runs_respect_the_cooldown_but_the_scheduler_does_not(session_factory):
    with session_factory() as db:
        pipeline.ingest_cycle(db, ingest=fake_ingest([]))
        with pytest.raises(pipeline.Busy):
            pipeline.ingest_cycle(db, manual=True, ingest=fake_ingest([]))
        pipeline.ingest_cycle(db, manual=False, ingest=fake_ingest([]))  # no exception


def test_a_running_cycle_blocks_both_manual_and_scheduled_runs(session_factory):
    calls = []
    assert pipeline._lock.acquire(blocking=False)
    try:
        with session_factory() as db:
            with pytest.raises(pipeline.Busy):
                pipeline.ingest_cycle(db, manual=False, ingest=fake_ingest(calls))
        assert pipeline.scheduled_cycle(session_factory, ingest=fake_ingest(calls)) is None
    finally:
        pipeline._lock.release()
    assert calls == []


def test_a_failing_watch_check_never_fails_the_ingest(session_factory, monkeypatch):
    def boom(db):
        raise RuntimeError("watch table is broken")
    monkeypatch.setattr(pipeline.watches, "check_watches", boom)
    with session_factory() as db:
        result = pipeline.ingest_cycle(db, ingest=fake_ingest([]))
    assert result.alerts == [] and result.results


def test_scheduled_cycle_ingests_then_enriches_until_the_backlog_is_empty(session_factory):
    waves = []

    def enrich(db):
        waves.append(1)
        return {"enriched": 3, "remaining": 5 if len(waves) < 3 else 0}

    result = pipeline.scheduled_cycle(session_factory, ingest=fake_ingest([]), enrich=enrich)
    assert result is not None and len(waves) == 3


def test_enrichment_stops_when_a_wave_makes_no_progress(session_factory):
    waves = []

    def enrich(db):
        waves.append(1)
        return {"enriched": 0, "remaining": 4}

    pipeline.enrich_backlog(session_factory, enrich)
    assert len(waves) == 1


def test_enrichment_failures_are_contained(session_factory):
    def enrich(db):
        raise RuntimeError("model is down")

    pipeline.enrich_backlog(session_factory, enrich)  # does not raise


def test_pending_is_defined_once_and_excludes_seeds(session_factory):
    with session_factory() as db:
        pending = db.query(Article).filter(*enrichment.pending_clauses()).all()
    assert [a.title for a in pending] == ["Waiting"]
    assert config.INGEST_COOLDOWN_SECONDS >= 0
