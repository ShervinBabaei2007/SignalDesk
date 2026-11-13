"""API integration tests using FastAPI's TestClient (SQLite in-memory)."""

import os
import sys
import tempfile
from pathlib import Path

# Use a throwaway database for tests
_test_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_dir}/test.db"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

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
