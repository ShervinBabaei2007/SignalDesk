"""Production-hardening tests: security headers, validation, ingest lock."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_security_headers_present():
    """Security headers are present on responses."""
    res = client.get("/api/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_health_reports_version_and_uptime():
    """Health reports the version and uptime."""
    body = client.get("/api/health").json()
    assert body["version"]
    assert body["uptime_seconds"] >= 0
    assert body["env"] in ("development", "production")


def test_feed_rejects_non_http_scheme():
    """Feeds with a non-http scheme are rejected."""
    res = client.post("/api/feeds", json={"name": "x", "url": "ftp://example.com/rss"})
    assert res.status_code == 422


def test_ingest_answers_429_when_the_pipeline_is_busy(monkeypatch):
    """A refused cycle becomes a friendly 429. (The cooldown rules themselves: tests/test_pipeline.py.)"""
    from app import pipeline

    def busy(db, *, manual, ingest=None):
        """Stand-in ingest cycle that always refuses as busy."""
        raise pipeline.Busy("An ingestion just ran — give the feeds a moment before refreshing again.")

    monkeypatch.setattr(pipeline, "ingest_cycle", busy)
    res = client.post("/api/ingest")
    assert res.status_code == 429
    assert "ingestion" in res.json()["detail"].lower()


def test_add_default_feeds_is_idempotent():
    """Adding the default feeds is idempotent."""
    from app.ingestion import DEFAULT_FEEDS

    assert len(DEFAULT_FEEDS) == 15  # the curated default list size
    assert not any("hnrss" in f["url"] for f in DEFAULT_FEEDS)  # aggregator: too noisy
    first = client.post("/api/feeds/defaults")
    assert first.status_code == 200
    urls = {f["url"] for f in client.get("/api/feeds").json()}
    assert {f["url"] for f in DEFAULT_FEEDS} <= urls
    assert client.post("/api/feeds/defaults").json() == []  # nothing left to add


def test_add_default_feeds_requires_token_when_configured(monkeypatch):
    """Adding the default feeds requires the token when one is configured."""
    from app import config

    monkeypatch.setattr(config, "API_TOKEN", "s3cret")
    assert client.post("/api/feeds/defaults").status_code == 401
    ok = client.post("/api/feeds/defaults", headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200
