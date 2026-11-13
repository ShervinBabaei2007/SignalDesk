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

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed_data import seed_if_empty  # noqa: E402

# TestClient does not run the lifespan in this Starlette version, so set up
# the schema and seed data explicitly for a hermetic test database.
Base.metadata.create_all(bind=engine)
with SessionLocal() as _db:
    seed_if_empty(_db)

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "healthy"
    assert body["articles"] > 0  # seeded automatically


def test_stats_shape():
    body = client.get("/api/stats").json()
    for key in ("total_articles", "total_sources", "avg_sentiment",
                "positive", "neutral", "negative", "topic_breakdown", "sentiment_7d"):
        assert key in body


def test_list_articles():
    res = client.get("/api/articles?limit=5")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 5
    assert len(body["items"]) == 5
    article = body["items"][0]
    assert set(article) >= {"id", "title", "url", "source", "topic", "sentiment", "sentiment_label"}


def test_search_filter():
    res = client.get("/api/articles?search=chip")
    assert res.status_code == 200
    for item in res.json()["items"]:
        assert "chip" in (item["title"] + (item["summary"] or "")).lower()


def test_sentiment_filter():
    items = client.get("/api/articles?sentiment=negative").json()["items"]
    assert items, "expected at least one negative seed article"
    assert all(i["sentiment"] < -0.15 for i in items)


def test_article_404():
    assert client.get("/api/articles/999999").status_code == 404


def test_feed_crud():
    created = client.post("/api/feeds", json={"name": "Test Feed", "url": "https://example.com/rss.xml"})
    assert created.status_code == 201
    feed_id = created.json()["id"]

    assert client.get("/api/feeds").status_code == 200
    assert client.delete(f"/api/feeds/{feed_id}").status_code == 204
    assert client.delete(f"/api/feeds/{feed_id}").status_code == 404


def test_duplicate_feed_rejected():
    client.post("/api/feeds", json={"name": "Dup Feed", "url": "https://dup.example.com/rss.xml"})
    res = client.post("/api/feeds", json={"name": "Dup Feed", "url": "https://dup.example.com/rss.xml"})
    assert res.status_code == 409


def test_invalid_feed_url():
    res = client.post("/api/feeds", json={"name": "Bad", "url": "not-a-url"})
    assert res.status_code == 422


def test_sort_orders():
    newest = client.get("/api/articles?order=newest").json()["items"]
    low = client.get("/api/articles?order=sentiment_low").json()["items"]
    assert newest[0]["id"] != low[0]["id"] or newest[0]["sentiment"] <= low[0]["sentiment"]
    assert low[0]["sentiment"] == min(i["sentiment"] for i in low)


def test_invalid_order_rejected():
    assert client.get("/api/articles?order=bogus").status_code == 422


def test_digest():
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
    from app.database import SessionLocal
    from sqlalchemy import select as sq
    from app.models import Article
    with SessionLocal() as db:
        missing = [a for a in db.execute(sq(Article)).scalars().all() if not a.keywords]
    assert missing == []


def test_csv_export():
    res = client.get("/api/articles/export.csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    lines = res.text.strip().splitlines()
    assert lines[0].startswith("id,title,source")
    assert len(lines) > 5


def test_article_detail_has_keywords():
    article = client.get("/api/articles?limit=1").json()["items"][0]
    detail = client.get(f"/api/articles/{article['id']}").json()
    assert "is_seed" in detail
    assert "keywords" in detail
