"""Production-hardening tests: security headers, validation, ingest lock."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_security_headers_present():
    res = client.get("/api/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_health_reports_version_and_uptime():
    body = client.get("/api/health").json()
    assert body["version"]
    assert body["uptime_seconds"] >= 0
    assert body["env"] in ("development", "production")


def test_feed_rejects_non_http_scheme():
    res = client.post("/api/feeds", json={"name": "x", "url": "ftp://example.com/rss"})
    assert res.status_code == 422


def test_ingest_cooldown_returns_429():
    """A second ingest inside the cooldown window is refused with a friendly message."""
    first = client.post("/api/ingest")
    assert first.status_code in (200, 429)  # first call may already be in cooldown from other tests
    second = client.post("/api/ingest")
    assert second.status_code == 429
    assert "ingestion" in second.json()["detail"].lower()


def test_add_default_feeds_is_idempotent():
    from app.ingestion import DEFAULT_FEEDS

    assert len(DEFAULT_FEEDS) == 12
    first = client.post("/api/feeds/defaults")
    assert first.status_code == 200
    urls = {f["url"] for f in client.get("/api/feeds").json()}
    assert {f["url"] for f in DEFAULT_FEEDS} <= urls
    assert client.post("/api/feeds/defaults").json() == []  # nothing left to add


def test_add_default_feeds_requires_token_when_configured(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "API_TOKEN", "s3cret")
    assert client.post("/api/feeds/defaults").status_code == 401
    ok = client.post("/api/feeds/defaults", headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200
