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

from app import clustering  # noqa: E402
from app.clustering import cluster_rows, title_terms  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Article  # noqa: E402

NOW = datetime.now(timezone.utc)


def _rows(*titles, gap_hours=1):
    return [(i + 1, t, f"Src{i}", NOW - timedelta(hours=gap_hours * i)) for i, t in enumerate(titles)]


def test_same_event_different_wording_clusters():
    clusters = cluster_rows(_rows(
        "FAA issues nationwide ground stop due to extraordinary circumstances",
        "FAA ground stop shuts down flights nationwide",
        "Apple unveils new MacBook with faster chip",
    ))
    assert len(clusters) == 1
    assert clusters[0].article_ids == (1, 2)
    assert clusters[0].sources == ("Src0", "Src1")


def test_unrelated_headlines_stay_apart():
    assert cluster_rows(_rows(
        "Apple announces new iPhone lineup",
        "Apple announces record quarterly earnings",
        "Bitcoin falls below key support level",
    )) == []


def test_clustering_is_transitive_and_id_is_smallest():
    clusters = cluster_rows(_rows(
        "Microsoft global outage hits Outlook and Teams users",
        "Microsoft outage: Outlook down for thousands of users",
        "Outlook outage Microsoft says Teams users recovering",
    ))
    assert len(clusters) == 1 and clusters[0].id == 1 and clusters[0].size == 3


def test_same_story_far_apart_in_time_is_not_merged():
    rows = _rows("Jensen Huang agrees to testify before Congress",
                 "Jensen Huang agrees to testify before Congress", gap_hours=100)
    assert cluster_rows(rows) == []


def test_terms_ignore_entities_plurals_and_stopwords():
    assert title_terms("Microsoft&#8217;s Outages") == title_terms("Microsoft outage")
    assert "the" not in title_terms("The big news")


def test_api_exposes_cluster_fields_filter_and_related():
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
    clustering._cache["key"] = None
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
