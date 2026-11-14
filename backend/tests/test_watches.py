"""Watchlists: alerts for stories you care about, once each."""

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_test_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_dir}/watches.db"
os.environ["INGEST_INTERVAL_MINUTES"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import clustering, notifications, watches  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Article, Watch, WatchAlert  # noqa: E402

NOW = datetime.now(timezone.utc)
client = TestClient(app)
_counter = [0]


def add_story(db, titles_sources, topic="World"):
    """Insert one report per (title, source) and reset the cluster cache."""
    for title, source in titles_sources:
        _counter[0] += 1
        db.add(Article(title=title, url=f"https://w.example/{_counter[0]}", source=source, topic=topic,
                       sentiment=0.0, published_at=NOW - timedelta(minutes=_counter[0]), is_seed=False))
    db.commit()
    clustering._cache["key"] = None


def reset_watches(db):
    db.query(WatchAlert).delete()
    db.query(Watch).delete()
    db.commit()


def setup_module(_):
    Base.metadata.create_all(bind=engine)


def test_term_matching_is_whole_word_and_case_insensitive():
    assert watches.term_matches("AI", "New AI chip announced")
    assert not watches.term_matches("AI", "He said it was fine")
    assert watches.term_matches("ground stop", "FAA orders a Ground Stop nationwide")
    assert watches.term_matches("S&P 500", "The S&P 500 rose")
    assert not watches.term_matches("oil", "boiling point")


def test_new_watch_ignores_old_stories_then_alerts_once_for_a_new_one():
    with SessionLocal() as db:
        reset_watches(db)
        add_story(db, [("Tsunami warning issued for Pacific coastline communities tonight", "Alpha"),
                       ("Pacific coastline communities told to evacuate after tsunami warning issued", "Beta")])
    created = client.post("/api/watches", json={"term": "tsunami"})
    assert created.status_code == 201
    assert created.json()["matches"] == 1  # today's story is visible as a match...
    with SessionLocal() as db:
        assert watches.check_watches(db, deliver=False) == []  # ...but it is not "news" for the new watch

        add_story(db, [("Tsunami drill planned for Japanese schools throughout next month", "Gamma"),
                       ("Japanese schools plan tsunami drill throughout next month, officials confirm", "Delta")])
        alerts = watches.check_watches(db, deliver=False)
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert["term"] == "tsunami" and alert["outlets"] == 2 and "drill" in alert["title"].lower()
        assert watches.check_watches(db, deliver=False) == []  # never alerts twice for the same story


def test_min_outlets_and_topic_are_respected():
    with SessionLocal() as db:
        reset_watches(db)
        client.post("/api/watches", json={"term": "avalanche", "min_outlets": 2})
        client.post("/api/watches", json={"term": "avalanche", "min_outlets": 1, "topic": "Science"})
        add_story(db, [("Avalanche buries mountain road near alpine ski resort overnight", "Alpha")], topic="World")
        alerts = watches.check_watches(db, deliver=False)
        # one outlet only: the 2+ outlet watch stays quiet, and the Science-only watch ignores a World story
        assert alerts == []
        add_story(db, [("Avalanche buries alpine mountain road close to ski resort overnight, officials say", "Beta")],
                  topic="World")
        alerts = watches.check_watches(db, deliver=False)
        assert [a["outlets"] for a in alerts] == [2]
        add_story(db, [("Researchers model avalanche triggers across steep snowfields using sensor networks", "Gamma")],
                  topic="Science")
        assert [a["term"] for a in watches.check_watches(db, deliver=False)] == ["avalanche"]


def test_alerts_are_delivered_to_configured_channels(monkeypatch):
    sent = []
    monkeypatch.setattr(notifications, "configured_channels", lambda: ["slack"])
    monkeypatch.setattr(notifications, "deliver_alert",
                        lambda subject, text: (sent.append((subject, text)), {"channels": ["slack"], "sent": ["slack"], "errors": []})[1])
    with SessionLocal() as db:
        reset_watches(db)
        client.post("/api/watches", json={"term": "meteorite", "min_outlets": 1})
        add_story(db, [("Meteorite lights up the night sky above northern coastal towns", "Alpha")])
        alerts = watches.check_watches(db)
        assert len(alerts) == 1 and len(sent) == 1
        assert "meteorite" in sent[0][0].lower() and "northern coastal towns" in sent[0][1]
        assert db.query(WatchAlert).filter_by(notified=True).count() == 1


def test_stories_carry_watch_matches_for_the_feed_badge():
    with SessionLocal() as db:
        reset_watches(db)
        add_story(db, [("Glacier lake outburst threatens remote valley settlements this week", "Alpha")])
    client.post("/api/watches", json={"term": "glacier lake", "min_outlets": 1})
    # the DB is shared with other test modules, so pick our story by title
    items = client.get("/api/stories?search=outburst&limit=20").json()["items"]
    ours = next(st for st in items if "outburst" in st["lead"]["title"].lower())
    assert ours["watch_matches"] == ["glacier lake"]
    everything = client.get("/api/stories?limit=100").json()["items"]
    assert any(st["watch_matches"] == [] for st in everything)  # unrelated stories carry no badge


def test_watch_api_validation_limits_toggle_and_delete(monkeypatch):
    with SessionLocal() as db:
        reset_watches(db)
    assert client.post("/api/watches", json={"term": "   "}).status_code == 422
    assert client.post("/api/watches", json={"term": "x", "topic": "Nonsense"}).status_code == 422
    assert client.post("/api/watches", json={"term": "x", "min_outlets": 0}).status_code == 422
    first = client.post("/api/watches", json={"term": "Quantum  computing", "topic": "Technology"})
    assert first.status_code == 201 and first.json()["term"] == "Quantum computing"  # whitespace tidied
    assert client.post("/api/watches", json={"term": "quantum computing", "topic": "Technology"}).status_code == 409

    wid = first.json()["id"]
    off = client.patch(f"/api/watches/{wid}", json={"is_active": False})
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert watches.active(SessionLocal()) == []
    assert client.patch("/api/watches/99999", json={"is_active": True}).status_code == 404

    assert client.delete(f"/api/watches/{wid}").status_code == 204
    assert client.delete(f"/api/watches/{wid}").status_code == 404
    assert client.get("/api/watches").json() == []

    monkeypatch.setattr(watches, "MAX_WATCHES", 2)
    client.post("/api/watches", json={"term": "one"})
    client.post("/api/watches", json={"term": "two"})
    assert client.post("/api/watches", json={"term": "three"}).status_code == 409


def test_watch_writes_require_a_token_when_configured(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "API_TOKEN", "s3cret")
    assert client.post("/api/watches", json={"term": "secure"}).status_code == 401
    ok = client.post("/api/watches", json={"term": "secure"}, headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 201
    assert client.get("/api/watches").status_code == 200  # reading stays public
    assert client.delete(f"/api/watches/{ok.json()['id']}").status_code == 401


def test_delivery_seam_marks_only_the_alerts_it_delivered():
    delivered = []

    def recording(alerts):
        delivered.append(alerts)
        return True

    with SessionLocal() as db:
        reset_watches(db)
        add_story(db, [("Caldera collapses near island resort, tourists evacuated by ferry", "Alpha"),
                       ("Tourists evacuated by ferry as caldera collapses near island resort", "Beta")])
        # Watch B existed already and baselined this story: its alert row is unnotified and must stay so.
        client.post("/api/watches", json={"term": "caldera", "min_outlets": 2})
        before = db.query(WatchAlert).count()
        assert before == 1
        # Watch A is created directly (no baseline), so the story is new to it.
        a = Watch(term="island resort", min_outlets=2, is_active=True)
        db.add(a)
        db.commit()
        alerts = watches.check_watches(db, notify=recording)
        assert [x["term"] for x in alerts] == ["island resort"] and len(delivered) == 1
        rows = {r.watch_id: r.notified for r in db.query(WatchAlert).all()}
        assert rows[a.id] is True
        assert [v for k, v in rows.items() if k != a.id] == [False]


def test_failed_delivery_leaves_alerts_unnotified():
    with SessionLocal() as db:
        reset_watches(db)
        client.post("/api/watches", json={"term": "typhoon", "min_outlets": 1})
        add_story(db, [("Typhoon forces airport closures across the southern archipelago", "Alpha")])
        assert len(watches.check_watches(db, notify=lambda alerts: False)) == 1
        assert db.query(WatchAlert).filter_by(notified=True).count() == 0


def test_story_matches_is_the_single_rule_for_counts_and_alerts():
    with SessionLocal() as db:
        reset_watches(db)
        add_story(db, [("Heatwave grips central plains as records fall for third day", "Alpha")])
        watch = Watch(term="heatwave", min_outlets=2, is_active=True)
        members = [m for k, ms in watches.recent_stories(db) for m in ms if "heatwave" in m.title.lower()]
        assert not watches.story_matches(watch, members)  # one outlet is not enough
        watch.min_outlets = 1
        assert watches.story_matches(watch, members)
