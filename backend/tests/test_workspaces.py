"""Private workspaces: each visitor's feeds, watches and articles are invisible to everyone else."""

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
from sqlalchemy import select  # noqa: E402

from app import config, ingestion, netguard, pipeline, story_index, workspace  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Article, Feed, Watch  # noqa: E402
from app.seed_data import seed_if_empty  # noqa: E402

Base.metadata.create_all(bind=engine)
with SessionLocal() as _db:
    seed_if_empty(_db, live=False)

client = TestClient(app)
REAL_CHECK_URL = netguard.check_url  # the autouse fixture below stubs the guard out of DNS-free tests


@pytest.fixture(autouse=True)
def workspaces_on(monkeypatch):
    """Turn workspaces on with a signing secret, and start each test from clean limits and caches."""
    monkeypatch.setattr(config, "SESSION_SECRET", "test-secret")
    monkeypatch.setattr(config, "API_TOKEN", "owner-token")
    monkeypatch.setattr(workspace, "creations", workspace.RateLimiter(1000))
    monkeypatch.setattr(pipeline, "INGEST_COOLDOWN_SECONDS", 0, raising=False)
    monkeypatch.setattr(config, "INGEST_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr(netguard, "check_url", lambda url: None)  # these tests do not touch DNS
    story_index.reset_cache()
    yield
    with SessionLocal() as db:  # leave no workspace rows behind for other test modules
        for model in (Watch, Feed, Article):
            db.execute(model.__table__.delete().where(model.workspace_id != ""))
        db.commit()


def new_workspace() -> dict:
    """Start a workspace and return the headers that act as it."""
    res = client.post("/api/workspace")
    assert res.status_code == 201
    return {"X-API-Key": res.json()["token"]}


def add_feed(headers, name="Hacker News", url="https://news.example/rss"):
    """Add a feed as the given visitor."""
    return client.post("/api/feeds", headers=headers, json={"name": name, "url": url})


def fake_feed(monkeypatch, links):
    """Make every fetched feed contain one entry per link, without touching the network."""
    entries = [SimpleNamespace(title=f"Story {i} about markets", link=link, summary="Markets rallied today.",
                               published_parsed=None, updated_parsed=None) for i, link in enumerate(links)]
    monkeypatch.setattr(ingestion.netguard, "fetch", lambda url, **kw: SimpleNamespace(content=b""))
    monkeypatch.setattr(ingestion.feedparser, "parse", lambda arg: SimpleNamespace(entries=entries))


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #

def test_workspace_tokens_cannot_be_forged_or_borrowed():
    _, token = workspace.issue()
    wid = workspace.verify(token)
    assert wid
    assert workspace.verify(token.replace(wid, "someone-else")) is None
    assert workspace.verify("owner-token") is None
    assert workspace.verify("demo.9999999999.abc") is None
    assert workspace.verify("ws.x") is None


def test_workspaces_are_off_without_a_secret(monkeypatch):
    monkeypatch.setattr(config, "SESSION_SECRET", "")
    assert client.post("/api/workspace").status_code == 404
    assert workspace.verify("ws.abc.def") is None


def test_creating_workspaces_is_rate_limited(monkeypatch):
    monkeypatch.setattr(workspace, "creations", workspace.RateLimiter(2))
    assert [client.post("/api/workspace").status_code for _ in range(3)] == [201, 201, 429]


def test_rate_limiter_window_slides():
    limiter = workspace.RateLimiter(1, window_seconds=10)
    assert limiter.allow("ip", now=0) and not limiter.allow("ip", now=5) and limiter.allow("ip", now=11)


# --------------------------------------------------------------------------- #
# Isolation
# --------------------------------------------------------------------------- #

def test_a_visitors_feeds_are_invisible_to_others_but_shared_feeds_are_visible_to_all():
    a, b = new_workspace(), new_workspace()
    assert add_feed(a).status_code == 201
    names = lambda headers: {f["name"]: f["shared"] for f in client.get("/api/feeds", headers=headers).json()}  # noqa: E731
    assert names(a)["Hacker News"] is False
    assert "Hacker News" not in names(b)
    assert "Hacker News" not in names({})  # nor the anonymous tour
    assert names(b)["BBC World"] is True  # the shared base feeds are everyone's


def test_two_visitors_can_add_the_same_feed():
    a, b = new_workspace(), new_workspace()
    assert add_feed(a).status_code == 201
    assert add_feed(b).status_code == 201
    assert add_feed(a).status_code == 409  # but not twice within one workspace


def test_a_visitor_cannot_delete_shared_feeds_or_someone_elses():
    a, b = new_workspace(), new_workspace()
    mine = add_feed(a).json()["id"]
    shared = next(f["id"] for f in client.get("/api/feeds", headers=a).json() if f["shared"])
    assert client.delete(f"/api/feeds/{shared}", headers=a).status_code == 404
    assert client.delete(f"/api/feeds/{mine}", headers=b).status_code == 404
    assert client.delete(f"/api/feeds/{mine}", headers=a).status_code == 204
    assert client.get("/api/feeds", headers={"X-API-Key": "owner-token"}).status_code == 200


def test_watchlists_are_private():
    a, b = new_workspace(), new_workspace()
    created = client.post("/api/watches", headers=a, json={"term": "chips", "min_outlets": 2})
    assert created.status_code == 201
    assert [w["term"] for w in client.get("/api/watches", headers=a).json()] == ["chips"]
    assert client.get("/api/watches", headers=b).json() == []
    assert client.get("/api/watches").json() == []
    watch_id = created.json()["id"]
    assert client.delete(f"/api/watches/{watch_id}", headers=b).status_code == 404
    assert client.patch(f"/api/watches/{watch_id}", headers=b, json={"is_active": False}).status_code == 404


def test_ingested_articles_stay_in_the_visitors_workspace(monkeypatch):
    a, b = new_workspace(), new_workspace()
    add_feed(a)
    fake_feed(monkeypatch, ["https://private.example/one", "https://private.example/two"])
    res = client.post("/api/ingest", headers=a)
    assert res.status_code == 200 and res.json()["added"] == 2

    def urls(headers):
        return {i["url"] for i in client.get("/api/articles?limit=100", headers=headers).json()["items"]}

    assert {"https://private.example/one", "https://private.example/two"} <= urls(a)
    assert not {u for u in urls(b) if "private.example" in u}
    assert not {u for u in urls({}) if "private.example" in u}
    # counts follow the same scope
    total = lambda headers: client.get("/api/stats", headers=headers).json()["total_articles"]  # noqa: E731
    assert total(a) == total(b) + 2


def test_two_visitors_can_ingest_the_same_story(monkeypatch):
    a, b = new_workspace(), new_workspace()
    add_feed(a)
    add_feed(b)
    fake_feed(monkeypatch, ["https://shared-story.example/x"])
    assert client.post("/api/ingest", headers=a).json()["added"] == 1
    assert client.post("/api/ingest", headers=b).json()["added"] == 1  # same URL, separate workspace


def test_a_workspace_ingest_fetches_only_its_own_feeds(monkeypatch):
    a = new_workspace()
    add_feed(a, name="Mine", url="https://mine.example/rss")
    fetched = []
    monkeypatch.setattr(ingestion.netguard, "fetch", lambda url, **kw: (fetched.append(url), SimpleNamespace(content=b""))[1])
    monkeypatch.setattr(ingestion.feedparser, "parse", lambda arg: SimpleNamespace(entries=[]))
    client.post("/api/ingest", headers=a)
    assert fetched == ["https://mine.example/rss"]  # never the shared feeds


def test_resetting_a_workspace_leaves_everyone_else_alone(monkeypatch):
    a, b = new_workspace(), new_workspace()
    for headers in (a, b):
        add_feed(headers)
        client.post("/api/watches", headers=headers, json={"term": "chips", "min_outlets": 2})
    base_articles = client.get("/api/stats").json()["total_articles"]
    assert client.delete("/api/workspace", headers=a).status_code == 204
    assert [f for f in client.get("/api/feeds", headers=a).json() if not f["shared"]] == []
    assert client.get("/api/watches", headers=a).json() == []
    assert any(not f["shared"] for f in client.get("/api/feeds", headers=b).json())
    assert len(client.get("/api/watches", headers=b).json()) == 1
    assert client.get("/api/stats").json()["total_articles"] == base_articles
    assert client.delete("/api/workspace").status_code == 401  # anonymous visitors have nothing to reset


def test_expired_workspaces_are_purged_but_shared_data_is_kept():
    a = new_workspace()
    add_feed(a)
    client.post("/api/watches", headers=a, json={"term": "chips", "min_outlets": 2})
    with SessionLocal() as db:
        shared_feeds = len(db.execute(select(Feed)).scalars().all())
        assert workspace.purge_expired(db) == 0  # fresh rows stay
        later = datetime.now(timezone.utc) + timedelta(days=config.WORKSPACE_TTL_DAYS + 1)
        assert workspace.purge_expired(db, now=later) >= 2
        assert len(db.execute(select(Feed)).scalars().all()) == shared_feeds  # shared feeds untouched
        assert db.execute(select(Feed).where(Feed.workspace_id != "")).first() is None
        assert db.execute(Watch.__table__.select().where(Watch.workspace_id != "")).first() is None


# --------------------------------------------------------------------------- #
# Limits and what stays owner-only
# --------------------------------------------------------------------------- #

def test_workspace_feed_and_watch_caps(monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE_MAX_FEEDS", 2)
    monkeypatch.setattr(config, "WORKSPACE_MAX_WATCHES", 1)
    a = new_workspace()
    assert [add_feed(a, name=f"F{i}", url=f"https://f{i}.example/rss").status_code for i in range(3)] == [201, 201, 409]
    assert client.post("/api/watches", headers=a, json={"term": "one", "min_outlets": 2}).status_code == 201
    assert client.post("/api/watches", headers=a, json={"term": "two", "min_outlets": 2}).status_code == 409


def test_workspace_article_cap(monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE_MAX_ARTICLES", 3)
    a = new_workspace()
    add_feed(a)
    fake_feed(monkeypatch, [f"https://cap.example/{i}" for i in range(6)])
    assert client.post("/api/ingest", headers=a).json()["added"] == 3


def test_unsafe_feed_urls_are_rejected(monkeypatch):
    monkeypatch.undo()  # use the real guard for this test
    monkeypatch.setattr(config, "SESSION_SECRET", "test-secret")
    monkeypatch.setattr(config, "API_TOKEN", "owner-token")
    monkeypatch.setattr(workspace, "creations", workspace.RateLimiter(1000))
    a = new_workspace()
    for bad in ("http://127.0.0.1/rss", "http://localhost/rss", "http://169.254.169.254/latest/meta-data",
                "http://10.0.0.5/rss", "http://[::1]/rss", "http://example.com:22/rss"):
        res = add_feed(a, name=bad, url=bad)
        assert res.status_code == 422, bad


def test_netguard_blocks_non_public_and_non_http_urls():
    for bad in ("file:///etc/passwd", "ftp://example.com/x", "http://127.0.0.1", "http://0.0.0.0",
                "http://192.168.1.1", "http://172.16.0.1", "http://100.64.0.1", "http://[fe80::1]/"):
        with pytest.raises(netguard.UnsafeURL):
            REAL_CHECK_URL(bad)


def test_owner_only_actions_reject_workspace_tokens():
    a = new_workspace()
    assert client.post("/api/feeds/defaults", headers=a).status_code == 401
    assert client.post("/api/digest/send", headers=a).status_code == 401
    assert client.post("/api/stories/1/brief", headers=a).status_code == 401
    assert client.post("/api/feeds", json={"name": "x", "url": "https://x.example/rss"}).status_code == 401


def test_a_workspace_watch_alert_is_never_delivered_to_the_owners_channels(monkeypatch):
    from app import watches
    called = []
    monkeypatch.setattr(watches, "deliver_to_channels", lambda alerts: called.append(alerts) or True)
    a = new_workspace()
    add_feed(a)
    client.post("/api/watches", headers=a, json={"term": "markets", "min_outlets": 1})
    fake_feed(monkeypatch, ["https://alert.example/1"])
    res = client.post("/api/ingest", headers=a)
    assert res.status_code == 200 and res.json()["alerts"]  # shown in the visitor's dashboard
    assert called == []  # but never sent to the owner's Slack or email
