"""Pipeline observability: recording cycles and summarising pipeline health."""

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

_test_dir = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_test_dir}/test.db")
os.environ["INGEST_INTERVAL_MINUTES"] = "0"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import ingestion, observability, pipeline  # noqa: E402
from app.database import Base, engine as app_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Article, Feed, FeedRun, PipelineRun  # noqa: E402

NOW = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)


@pytest.fixture()
def db():
    """In-memory database."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as session:
        yield session


def result(feed, fetched=10, added=4, error=None, latency_ms=300):
    """One per-feed ingest result."""
    return {"feed": feed, "fetched": fetched, "added": added, "skipped": fetched - added, "error": error,
            "latency_ms": latency_ms}


def test_percentile_is_nearest_rank():
    """Percentiles pick an actual sample by nearest rank and return 0 for no data."""
    assert observability.percentile([], 95) == 0
    assert observability.percentile([5], 50) == 5
    assert observability.percentile(list(range(1, 101)), 95) == 95
    assert observability.percentile([10, 20, 30, 40], 50) == 20


def test_record_cycle_stores_the_run_and_one_row_per_feed(db):
    """A recorded cycle saves run totals plus a success or failure row for each feed."""
    run_id = observability.record_cycle(db, kind="scheduled", duration_seconds=2.5, alerts=1,
                                        results=[result("BBC"), result("Dead", fetched=0, added=0, error="HTTP 503")])
    run = db.get(PipelineRun, run_id)
    assert (run.kind, run.duration_ms, run.feeds_ok, run.feeds_failed, run.added, run.alerts) == ("scheduled", 2500, 1, 1, 4, 1)
    rows = {r.feed: r for r in db.execute(select(FeedRun)).scalars()}
    assert rows["Dead"].ok is False and rows["Dead"].error == "HTTP 503" and rows["BBC"].ok is True


def test_visitor_workspaces_are_never_recorded(db):
    """Cycles run from a visitor workspace leave no pipeline history."""
    db.info["workspace"] = "visitor1"
    assert observability.record_cycle(db, kind="manual", duration_seconds=1, results=[result("Mine")]) is None
    assert db.execute(select(PipelineRun)).first() is None


def test_recording_failures_never_break_an_ingest(db, monkeypatch):
    """A database error while recording is swallowed and returns None."""
    # A lambda cannot raise, so throw into an empty generator to simulate the failure.
    monkeypatch.setattr(db, "flush", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    assert observability.record_cycle(db, kind="manual", duration_seconds=1, results=[result("BBC")]) is None


def test_summary_reports_latency_failures_throughput_and_extraction(db):
    """The health summary computes run latency, failure rates, throughput, extraction success and backlog."""
    # Four hourly runs (one failed); the Flaky feed fails on every other run.
    for i, (duration, ok) in enumerate([(1000, True), (3000, True), (9000, True), (500, False)]):
        run = PipelineRun(kind="scheduled", started_at=NOW - timedelta(hours=i + 1), duration_ms=duration, ok=ok,
                          feeds_ok=2, feeds_failed=0, fetched=20, added=5)
        db.add(run)
        db.flush()
        db.add(FeedRun(run_id=run.id, feed="BBC", at=run.started_at, ok=True, latency_ms=200 * (i + 1), added=5))
        db.add(FeedRun(run_id=run.id, feed="Flaky", at=run.started_at, ok=i % 2 == 0,
                       error=None if i % 2 == 0 else "HTTP 500", latency_ms=100))
    # Three full-page extractions and one fallback give a 75% success rate.
    for i, extraction in enumerate(["page", "page", "page", "fallback"]):
        db.add(Article(title=f"t{i}", url=f"https://x.test/{i}", source="BBC", topic="World", sentiment=0.0,
                       is_seed=False, extraction=extraction, enriched_at=NOW - timedelta(hours=1)))
    db.add(Article(title="waiting", url="https://x.test/w", source="BBC", topic="World", sentiment=0.0, is_seed=False))
    db.commit()

    s = observability.summary(db, hours=24, now=NOW)
    assert s["runs"]["total"] == 4 and s["runs"]["failed"] == 1 and s["runs"]["success_rate"] == 0.75
    assert s["runs"]["p50_ms"] == 1000 and s["runs"]["p95_ms"] == 9000
    assert s["runs"]["minutes_since_ok"] == 60
    assert s["throughput"]["added"] == 20 and s["throughput"]["per_hour"] == round(20 / 24, 2)
    assert len(s["throughput"]["series"]) == 4
    flaky = next(f for f in s["feeds"]["items"] if f["feed"] == "Flaky")
    assert flaky["failure_rate"] == 0.5 and flaky["last_error"] == "HTTP 500"
    assert s["feeds"]["items"][0]["feed"] == "Flaky"  # the unhealthy feeds come first
    assert (s["feeds"]["ok"], s["feeds"]["failing"]) == (1, 1)
    assert s["extraction"] == {"page": 3, "fallback": 1, "success_rate": 0.75}
    assert s["backlog"]["awaiting_enrichment"] == 1


def test_summary_of_an_empty_pipeline_is_all_zeros_not_an_error(db):
    """With no history the summary returns zeros and None rates rather than dividing by zero."""
    s = observability.summary(db, hours=24, now=NOW)
    assert s["runs"]["total"] == 0 and s["runs"]["success_rate"] is None and s["runs"]["minutes_since_ok"] is None
    assert s["extraction"]["success_rate"] is None and s["feeds"]["items"] == []


def test_old_history_is_purged(db):
    """Runs and feed rows older than the retention window are deleted while recent runs stay."""
    run = PipelineRun(kind="scheduled", started_at=NOW - timedelta(days=40), duration_ms=1)
    db.add(run)
    db.flush()
    db.add(FeedRun(run_id=run.id, feed="BBC", at=NOW - timedelta(days=40)))
    db.add(PipelineRun(kind="scheduled", started_at=NOW - timedelta(days=1), duration_ms=1))
    db.commit()
    assert observability.purge_old(db, now=NOW) == 2
    assert len(db.execute(select(PipelineRun)).scalars().all()) == 1


def test_a_dead_feed_is_reported_as_a_failure_not_zero_new_articles(db, monkeypatch):
    """Network errors and HTTP failures come back as errors, while an empty healthy feed does not."""
    dead = SimpleNamespace(entries=[], bozo=True, bozo_exception=OSError("name resolution failed"), status=None)
    monkeypatch.setattr(ingestion.feedparser, "parse", lambda url: dead)
    stats = ingestion.ingest_feed(db, "https://dead.example/rss", "Dead")
    assert "name resolution failed" in stats["error"] and "latency_ms" in stats
    gone = SimpleNamespace(entries=[], bozo=False, status=503)
    monkeypatch.setattr(ingestion.feedparser, "parse", lambda url: gone)
    assert ingestion.ingest_feed(db, "https://down.example/rss", "Down")["error"] == "HTTP 503"
    empty = SimpleNamespace(entries=[], bozo=False, status=200)  # a healthy feed with nothing new is not a failure
    monkeypatch.setattr(ingestion.feedparser, "parse", lambda url: empty)
    assert "error" not in ingestion.ingest_feed(db, "https://quiet.example/rss", "Quiet")


def test_a_pipeline_cycle_records_itself(db, monkeypatch):
    """A finished ingest cycle writes its own pipeline run row."""
    db.add(Feed(name="BBC", url="https://bbc.example/rss", is_active=True))
    db.commit()
    monkeypatch.setattr(pipeline, "_last_finished", 0.0)
    fake = lambda session, feeds, feed_rows=None: [result("BBC")]  # noqa: E731
    pipeline.ingest_cycle(db, manual=True, ingest=fake)
    run = db.execute(select(PipelineRun)).scalar_one()
    assert run.kind == "manual" and run.added == 4 and run.duration_ms >= 0


def test_a_crashing_cycle_is_recorded_as_failed_and_still_raises(db, monkeypatch):
    """A cycle that crashes is saved as a failed run with its error, and the exception still propagates."""
    monkeypatch.setattr(pipeline, "_last_finished", 0.0)

    def boom(session, feeds, feed_rows=None):
        """Stand-in ingest that always crashes."""
        raise RuntimeError("feeds exploded")

    with pytest.raises(RuntimeError):
        pipeline.ingest_cycle(db, manual=False, ingest=boom)
    run = db.execute(select(PipelineRun)).scalar_one()
    assert run.ok is False and "feeds exploded" in run.error


def test_the_observability_endpoint_serves_the_summary_to_anyone():
    """The public observability endpoint returns the summary without a token and validates the window."""
    Base.metadata.create_all(bind=app_engine)  # the test client does not run the app's startup
    client = TestClient(app)
    res = client.get("/api/observability?hours=6")
    assert res.status_code == 200
    body = res.json()
    assert body["window_hours"] == 6 and {"runs", "throughput", "feeds", "extraction", "backlog"} <= set(body)
    assert client.get("/api/observability?hours=0").status_code == 422
