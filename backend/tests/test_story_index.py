"""The story index: keys, the shared window, and hot ranking on plain data."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import story_index, stories  # noqa: E402
from app.clustering import Cluster  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import Article  # noqa: E402

NOW = datetime.now(timezone.utc)


def test_story_key_round_trips_and_distinguishes_clusters_from_lone_reports():
    cluster = Cluster(id=7, article_ids=(7, 9), sources=("A", "B"))
    assert story_index.story_key(cluster, 9) == "c7"
    assert story_index.story_key(None, 9) == "a9"
    parsed = story_index.parse_story_key("c7")
    assert (parsed.is_cluster, parsed.id, str(parsed)) == (True, 7, "c7")
    lone = story_index.parse_story_key("a9")
    assert (lone.is_cluster, lone.id, str(lone)) == (False, 9, "a9")


def _member(topic="World", sentiment=0.0, hours_ago=1.0):
    return SimpleNamespace(topic=topic, sentiment=sentiment,
                           published_at=NOW - timedelta(hours=hours_ago), ingested_at=NOW)


def test_hot_ranking_prefers_outlets_and_recency_and_skips_single_outlet_stories():
    fresh = Cluster(id=1, article_ids=(1, 2), sources=("A", "B"), title="Fresh", lead_id=1)
    big_but_old = Cluster(id=3, article_ids=(3, 4, 5), sources=("A", "B", "C"), title="Old", lead_id=3)
    one_outlet = Cluster(id=6, article_ids=(6, 7), sources=("A",), title="Echo", lead_id=6)
    info = {1: _member(hours_ago=1), 2: _member(hours_ago=2),
            3: _member(hours_ago=60), 4: _member(hours_ago=61), 5: _member(hours_ago=62),
            6: _member(), 7: _member()}
    ranked = story_index.rank_hot([big_but_old, one_outlet, fresh], info, NOW)
    assert [c.id for c, _ in ranked] == [1, 3]  # a story from one outlet is never hot
    assert ranked[0][1]["outlets"] == 2 and ranked[0][1]["reports"] == 2


def test_hot_ranking_summarises_topic_and_sentiment():
    cluster = Cluster(id=1, article_ids=(1, 2, 3), sources=("A", "B"), title="T", lead_id=1)
    info = {1: _member("Tech", 0.4), 2: _member("Tech", 0.2), 3: _member("World", 0.0)}
    (_, story), = story_index.rank_hot([cluster], info, NOW)
    assert story["topic"] == "Tech" and story["avg_sentiment"] == pytest.approx(0.2)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as session:
        rows = [("Quake strikes coastal city overnight, hundreds evacuated", "Alpha"),
                ("Hundreds evacuated as quake strikes coastal city overnight", "Beta"),
                ("Local bakery wins national bread award this weekend", "Gamma")]
        for i, (title, source) in enumerate(rows):
            session.add(Article(title=title, url=f"https://x.example/{i}", source=source, topic="World",
                                sentiment=0.0, published_at=NOW - timedelta(minutes=i), is_seed=False))
        session.add(Article(title="Demo seed", url="https://x.example/seed", source="Seed", topic="World",
                            sentiment=0.0, published_at=NOW, is_seed=True))
        session.commit()
        story_index.reset_cache()
        yield session
        story_index.reset_cache()


def test_recent_stories_use_the_same_keys_as_the_feed_and_skip_seeds(db):
    recent = dict(story_index.recent_stories(db))
    ordered = [a.id for a in db.query(Article).filter(Article.is_seed.is_(False)).order_by(Article.id.desc())]
    page = stories.build_page(db, ordered, 0, 20)
    assert set(recent) == {s["key"] for s in page["stories"]}
    assert sorted(len(m) for m in recent.values()) == [1, 2]
    assert all(not a.is_seed for members in recent.values() for a in members)


def test_the_window_is_read_once_per_article_set(db, monkeypatch):
    story_index.recent_stories(db)  # primes the cache
    calls = []
    real = story_index.cluster_rows
    monkeypatch.setattr(story_index, "cluster_rows", lambda rows: (calls.append(1), real(rows))[1])
    story_index.recent_stories(db)
    story_index.get_clusters(db)
    story_index.annotate(db, [])
    assert calls == []  # nothing re-clustered: every caller shares the cached window
