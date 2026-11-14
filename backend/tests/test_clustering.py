"""Story clustering: grouping logic and API surface."""

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_test_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_dir}/cluster.db"
os.environ["INGEST_INTERVAL_MINUTES"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import story_index  # noqa: E402
from app.clustering import cluster_rows, title_terms  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Article  # noqa: E402

NOW = datetime.now(timezone.utc)


def _rows(*titles, gap_hours=1):
    """Build clustering input rows from titles spaced by `gap_hours`."""
    return [(i + 1, t, f"Src{i}", NOW - timedelta(hours=gap_hours * i)) for i, t in enumerate(titles)]


def test_same_event_different_wording_clusters():
    """Headlines about the same event with different wording cluster together."""
    clusters = cluster_rows(_rows(
        "FAA issues nationwide ground stop due to extraordinary circumstances",
        "FAA ground stop shuts down flights nationwide",
        "Apple unveils new MacBook with faster chip",
    ))
    assert len(clusters) == 1
    assert clusters[0].article_ids == (1, 2)
    assert clusters[0].sources == ("Src0", "Src1")


def test_unrelated_headlines_stay_apart():
    """Unrelated headlines stay in separate stories."""
    assert cluster_rows(_rows(
        "Apple announces new iPhone lineup",
        "Apple announces record quarterly earnings",
        "Bitcoin falls below key support level",
    )) == []


def test_clustering_is_transitive_and_id_is_smallest():
    """Clustering is transitive and the cluster id is the smallest article id."""
    clusters = cluster_rows(_rows(
        "Microsoft global outage hits Outlook and Teams users",
        "Microsoft outage: Outlook down for thousands of users",
        "Outlook outage Microsoft says Teams users recovering",
    ))
    assert len(clusters) == 1 and clusters[0].id == 1 and clusters[0].size == 3


def test_same_story_far_apart_in_time_is_not_merged():
    """The same story published far apart in time is not merged."""
    rows = _rows("Jensen Huang agrees to testify before Congress",
                 "Jensen Huang agrees to testify before Congress", gap_hours=100)
    assert cluster_rows(rows) == []


def test_terms_ignore_entities_plurals_and_stopwords():
    """Title terms ignore entities, plurals and stopwords."""
    assert title_terms("Microsoft&#8217;s Outages") == title_terms("Microsoft outage")
    assert "the" not in title_terms("The big news")


def test_api_exposes_cluster_fields_filter_and_related():
    """The API exposes cluster fields, the cluster filter and related reports."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for i, (title, src) in enumerate([
            ("Huge Atlantic storm forces airport closures across Europe", "Alpha"),
            ("Atlantic storm closes airports across Europe", "Beta"),
            ("Local team wins championship after dramatic final", "Gamma"),
        ]):
            db.add(Article(title=title, url=f"https://x.example/{i}", source=src, topic="World",
                           sentiment=0.0, published_at=NOW, is_seed=False))
        db.commit()
    story_index.reset_cache()
    client = TestClient(app)

    items = client.get("/api/articles?limit=50").json()["items"]
    by_title = {a["title"]: a for a in items}
    storm = by_title["Atlantic storm closes airports across Europe"]
    assert storm["cluster_size"] == 2 and sorted(storm["cluster_sources"]) == ["Alpha", "Beta"]
    assert by_title["Local team wins championship after dramatic final"]["cluster_size"] == 1

    filtered = client.get(f"/api/articles?cluster={storm['cluster_id']}").json()
    assert filtered["total"] == 2

    detail = client.get(f"/api/articles/{storm['id']}").json()
    assert [r["source"] for r in detail["related"]] == ["Alpha"]


def test_related_items_carry_sentiment_and_snippet():
    """Related items carry sentiment and a snippet."""
    client = TestClient(app)
    items = client.get("/api/articles?limit=50").json()["items"]
    storm = next(a for a in items if a["cluster_size"] == 2)
    related = client.get(f"/api/articles/{storm['id']}").json()["related"][0]
    assert {"sentiment", "summary", "summary_deep"} <= related.keys()


def test_lead_headline_is_the_most_representative_one():
    """The lead headline is the one most like the others in the story."""
    clusters = cluster_rows([
        (1, "Microsoft outage hits Outlook and Teams worldwide", "A", NOW),
        (2, "Microsoft global outage takes down Outlook and Teams", "B", NOW),
        (3, "Why is Microsoft's outage lasting so long, and will Outlook emails be lost", "C", NOW),
    ])
    assert len(clusters) == 1
    assert clusters[0].title in ("Microsoft outage hits Outlook and Teams worldwide",
                                 "Microsoft global outage takes down Outlook and Teams")
    assert clusters[0].lead_id in (1, 2)


def test_trending_api_ranks_multi_outlet_stories_and_skips_single_source():
    """The trending API ranks multi-outlet stories and skips single-source ones."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for i, (title, src) in enumerate([
            ("Volcano eruption closes Iceland airspace for travellers", "Alpha"),
            ("Iceland volcano eruption closes airspace for travellers", "Beta"),
            ("Iceland airspace closed after volcano eruption", "Gamma"),
            ("Quarterly tax filing deadline extended for small firms", "Alpha"),
            ("Small firms get extended quarterly tax filing deadline", "Alpha"),
        ]):
            db.add(Article(title=title, url=f"https://t.example/{i}", source=src, topic="World",
                           sentiment=-0.3, published_at=NOW, is_seed=False))
        db.commit()
    story_index.reset_cache()
    client = TestClient(app)
    stories = client.get("/api/trending?limit=20").json()
    # the DB is shared with other test modules, so find our story rather than assuming it ranks first
    top = next(st for st in stories if "volcano" in st["title"].lower())
    assert top["outlets"] == 3 and top["reports"] == 3
    assert {"cluster_id", "article_id", "topic", "avg_sentiment", "latest_at"} <= top.keys()
    # the two-article story from a single outlet is not "hot"
    assert all("tax" not in s["title"].lower() for s in stories)
    assert client.get(f"/api/articles?cluster={top['cluster_id']}").json()["total"] == 3


def test_hot_filter_matches_the_union_of_hot_stories():
    """The hot filter matches the union of the hot stories."""
    client = TestClient(app)
    stories = client.get("/api/trending").json()
    assert stories
    expected = set()
    for s in stories:
        page = client.get(f"/api/articles?cluster={s['cluster_id']}&limit=100").json()
        expected |= {a["id"] for a in page["items"]}
    hot = client.get("/api/articles?hot=1&limit=100").json()
    assert {a["id"] for a in hot["items"]} == expected
    assert hot["total"] == sum(s["reports"] for s in stories)

