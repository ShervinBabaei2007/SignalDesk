"""API integration tests using FastAPI's TestClient (SQLite in-memory)."""

import os
import sys
import tempfile
from pathlib import Path

# Use a throwaway database for tests, disable background scheduler
_test_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_dir}/test.db"
os.environ["INGEST_INTERVAL_MINUTES"] = "0"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import pipeline  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Article  # noqa: E402
from app.seed_data import seed_if_empty  # noqa: E402

# TestClient does not run the lifespan in this Starlette version, so set up
# the schema and seed data explicitly for a hermetic test database.
Base.metadata.create_all(bind=engine)
with SessionLocal() as _db:
    seed_if_empty(_db, live=False)

client = TestClient(app)


def test_health():
    """The health endpoint reports a healthy status."""
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "healthy"
    assert body["articles"] > 0  # seeded automatically


def test_stats_shape():
    """The stats endpoint returns the expected fields."""
    body = client.get("/api/stats").json()
    for key in ("total_articles", "total_sources", "avg_sentiment",
                "positive", "neutral", "negative", "topic_breakdown", "sentiment_7d"):
        assert key in body


def test_list_articles():
    """Listing articles returns a page of items."""
    res = client.get("/api/articles?limit=5")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 5
    assert len(body["items"]) == 5
    article = body["items"][0]
    assert set(article) >= {"id", "title", "url", "source", "topic", "sentiment", "sentiment_label"}


def test_search_filter():
    """The search filter narrows results to matching articles."""
    res = client.get("/api/articles?search=chip")
    assert res.status_code == 200
    for item in res.json()["items"]:
        assert "chip" in (item["title"] + (item["summary"] or "")).lower()


def test_sentiment_filter():
    """The sentiment filter returns only that sentiment."""
    items = client.get("/api/articles?sentiment=negative").json()["items"]
    assert items, "expected at least one negative seed article"
    assert all(i["sentiment"] < -0.15 for i in items)


def test_article_404():
    """An unknown article id returns 404."""
    assert client.get("/api/articles/999999").status_code == 404


def test_feed_crud():
    """A feed can be created, listed and deleted."""
    created = client.post("/api/feeds", json={"name": "Test Feed", "url": "https://example.com/rss.xml"})
    assert created.status_code == 201
    feed_id = created.json()["id"]

    assert client.get("/api/feeds").status_code == 200
    assert client.delete(f"/api/feeds/{feed_id}").status_code == 204
    assert client.delete(f"/api/feeds/{feed_id}").status_code == 404


def test_duplicate_feed_rejected():
    """Adding the same feed twice is rejected."""
    client.post("/api/feeds", json={"name": "Dup Feed", "url": "https://dup.example.com/rss.xml"})
    res = client.post("/api/feeds", json={"name": "Dup Feed", "url": "https://dup.example.com/rss.xml"})
    assert res.status_code == 409


def test_invalid_feed_url():
    """A malformed feed URL is rejected."""
    res = client.post("/api/feeds", json={"name": "Bad", "url": "not-a-url"})
    assert res.status_code == 422


def test_sort_orders():
    """Each sort order returns results in that order."""
    newest = client.get("/api/articles?order=newest").json()["items"]
    low = client.get("/api/articles?order=sentiment_low").json()["items"]
    assert newest[0]["id"] != low[0]["id"] or newest[0]["sentiment"] <= low[0]["sentiment"]
    assert low[0]["sentiment"] == min(i["sentiment"] for i in low)


def test_invalid_order_rejected():
    """An unknown sort order is rejected with 422."""
    assert client.get("/api/articles?order=bogus").status_code == 422


def test_digest():
    """The daily brief endpoint returns its headline and sections."""
    body = client.get("/api/digest").json()
    for key in ("generated_at", "window_label", "avg_sentiment", "headline",
                "topic_breakdown", "top_positive", "top_negative"):
        assert key in body
    assert body["total_articles"] > 0
    assert body["headline"]
    for item in body["top_positive"]:
        assert item["sentiment"] > 0.15
    for item in body["top_negative"]:
        assert item["sentiment"] < -0.15


def test_backfill_keywords():
    """All articles should end up with keywords after startup backfill."""
    with SessionLocal() as db:
        missing = [a for a in db.execute(select(Article)).scalars().all() if not a.keywords]
    assert missing == []


def test_summarize_endpoint_always_returns_summary():
    """Seeds skip network fetch and get a clean summary from stored text."""
    article = client.get("/api/articles?limit=1").json()["items"][0]
    res = client.post(f"/api/articles/{article['id']}/summarize")
    assert res.status_code == 200
    body = res.json()
    assert body["summary_deep"]
    assert body["enriched_at"]


def test_csv_export():
    """The CSV export returns a header and rows."""
    res = client.get("/api/articles/export.csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    lines = res.text.strip().splitlines()
    assert lines[0].startswith("id,title,source")
    assert len(lines) > 5


def test_article_detail_has_keywords():
    """Article detail includes the keyword list."""
    article = client.get("/api/articles?limit=1").json()["items"][0]
    detail = client.get(f"/api/articles/{article['id']}").json()
    assert "is_seed" in detail
    assert "keywords" in detail


def test_cron_ingest_rejects_missing_or_wrong_secret(monkeypatch):
    """The cron endpoint is closed when no secret is configured or the bearer token is wrong."""
    monkeypatch.setattr("app.main.config.CRON_SECRET", "")
    assert client.get("/api/cron/ingest").status_code == 401
    monkeypatch.setattr("app.main.config.CRON_SECRET", "s3cret")
    assert client.get("/api/cron/ingest", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_cron_ingest_runs_a_cycle_with_the_right_secret(monkeypatch):
    """A correct bearer token runs one scheduled cycle and reports the result."""
    monkeypatch.setattr("app.main.config.CRON_SECRET", "s3cret")
    monkeypatch.setattr("app.main.pipeline.scheduled_cycle", lambda: None)
    res = client.get("/api/cron/ingest", headers={"Authorization": "Bearer s3cret"})
    assert res.status_code == 200
    assert res.json() == {"ran": False, "added": 0}


def test_postgres_urls_use_the_psycopg_driver():
    """Plain postgres:// and postgresql:// URLs are rewritten for the psycopg 3 driver."""
    from app.database import _normalize_url
    assert _normalize_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert _normalize_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert _normalize_url("sqlite:///x.db") == "sqlite:///x.db"


def test_demo_session_is_off_by_default(monkeypatch):
    """Without DEMO_MODE the demo session endpoint does not exist."""
    monkeypatch.setattr("app.main.config.DEMO_MODE", False)
    assert client.post("/api/demo/session").status_code == 404


def test_demo_token_can_ingest_but_not_edit_feeds(monkeypatch):
    """A demo token runs an ingest, while every other write still needs the real API token."""
    monkeypatch.setattr("app.main.config.DEMO_MODE", True)
    monkeypatch.setattr("app.main.config.API_TOKEN", "real-token")
    token = client.post("/api/demo/session").json()["token"]
    assert token and token != "real-token"
    headers = {"X-API-Key": token}
    assert client.post("/api/feeds", headers=headers, json={"name": "x", "url": "https://x.test/rss"}).status_code == 401
    assert client.post("/api/ingest", headers={"X-API-Key": "wrong"}).status_code == 401

    def busy(db, manual):
        raise pipeline.Busy("busy")

    monkeypatch.setattr("app.main.pipeline.ingest_cycle", busy)
    assert client.post("/api/ingest", headers=headers).status_code == 429  # got past auth into the pipeline


def test_demo_tokens_expire_and_reject_tampering():
    """Expired, forged or differently-keyed demo tokens are invalid."""
    from app import demo
    token = demo.issue("secret", 60, now=1000)
    assert demo.is_valid(token, "secret", now=1030)
    assert not demo.is_valid(token, "secret", now=1061)
    assert not demo.is_valid(token, "other", now=1030)
    assert not demo.is_valid(token.replace("demo.1060", "demo.9999999999"), "secret", now=1030)
    assert not demo.is_valid("real-token", "secret", now=1030)
