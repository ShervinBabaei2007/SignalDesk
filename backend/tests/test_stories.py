"""Stories API: grouping reports of one event, best-informed first."""

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_test_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_dir}/stories.db"
os.environ["INGEST_INTERVAL_MINUTES"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import story_index  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Article  # noqa: E402

NOW = datetime.now(timezone.utc)
client = TestClient(app)

GLACIER = [  # same event, three outlets; the middle one is the most informative
    ("Alpine glacier collapse buries mountain village in Switzerland", "Aoutlet", 30.0, "x" * 500, -0.6, "World"),
    ("Swiss mountain village buried after alpine glacier collapse", "Boutlet", 90.0, "x" * 6000, -0.8, "World"),
    ("Glacier collapse buries Swiss alpine village in the mountains", "Coutlet", 60.0, "x" * 3000, -0.7, "World"),
]
SOLO = ("Quartz markets rally after unexpected interest rate decision", "Doutlet", 70.0, "x" * 4000, 0.4, "Business")
OTHER = [  # a second event, thinner coverage overall
    ("Marathon organisers unveil record entry numbers for spring race", "Aoutlet", 20.0, None, 0.5, "Sports"),
    ("Spring marathon organisers unveil record numbers of race entries", "Eoutlet", 25.0, None, 0.4, "Sports"),
]


MINE: list[int] = []  # ids of this module's articles; the DB is shared with other test modules


def setup_module(_):
    """Create the tables and seed the test articles once for this module."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for i, (title, src, score, text, sent, topic) in enumerate(GLACIER + [SOLO] + OTHER):
            db.add(Article(title=title, url=f"https://s.example/{i}", source=src, topic=topic, sentiment=sent,
                           info_score=score, full_text=text, published_at=NOW - timedelta(minutes=i * 5),
                           is_seed=False))
        db.commit()
        MINE.extend(a.id for a in db.query(Article).filter(Article.url.like("https://s.example/%")))
    story_index.reset_cache()


def stories(**params):
    """Fetch /api/stories with the given params, restricted to the test articles."""
    params.setdefault("ids", ",".join(map(str, MINE)))
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    res = client.get(f"/api/stories?{qs}")
    assert res.status_code == 200, res.text
    return res.json()


def glacier_story(page):
    """Find the glacier story in a page of stories."""
    return next(s for s in page["items"] if "glacier" in s["lead"]["title"].lower())


def test_reports_of_one_event_become_one_story_led_by_the_best_informed():
    """Reports of one event become one story led by the best-informed report."""
    page = stories(limit=50)
    glacier = glacier_story(page)
    assert glacier["report_count"] == 3 and glacier["outlets"] == 3
    assert glacier["lead"]["source"] == "Boutlet" and glacier["best_score"] == 90.0
    # the others follow in descending information score
    assert [o["source"] for o in glacier["others"]] == ["Coutlet", "Aoutlet"]
    assert [o["info_score"] for o in glacier["others"]] == [60.0, 30.0]


def test_pagination_counts_stories_not_articles():
    """Pagination counts stories, not articles."""
    page = stories(limit=50)
    assert page["total"] == 3  # glacier, solo, marathon
    assert page["article_total"] == 6
    first = stories(limit=2, offset=0)
    second = stories(limit=2, offset=2)
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert first["total"] == second["total"] == 3
    keys = [s["key"] for s in first["items"] + second["items"]]
    assert len(set(keys)) == 3  # no story repeated across pages


def test_single_reports_are_stories_of_one():
    """Single reports are stories of one."""
    solo = next(s for s in stories(limit=50)["items"] if s["lead"]["source"] == "Doutlet")
    assert solo["report_count"] == 1 and solo["others"] == [] and solo["cluster_id"] is None


def test_most_informative_order_ranks_stories_by_their_best_report():
    """The most-informative order ranks stories by their best report."""
    items = stories(limit=50, order="info")["items"]
    assert [s["best_score"] for s in items] == sorted((s["best_score"] for s in items), reverse=True)
    assert items[0]["best_score"] == 90.0


def test_filters_apply_to_reports_before_grouping():
    # a topic filter keeps only matching reports, so the marathon story is the only one left
    """Filters apply to reports before they are grouped."""
    only = stories(topic="Sports", limit=50)
    assert only["total"] == 1 and only["article_total"] == 2
    # the sentiment filter must also be reflected in the total (it used to be ignored)
    negative = client.get(f"/api/articles?sentiment=negative&limit=100&ids={','.join(map(str, MINE))}").json()
    assert negative["total"] == len(negative["items"]) == 3


def test_ids_filter_and_validation():
    """The ids filter works and invalid ids are rejected."""
    page = stories(limit=50)
    solo_id = next(s for s in page["items"] if s["cluster_id"] is None and s["lead"]["source"] == "Doutlet")["lead"]["id"]
    res = stories(ids=str(solo_id), limit=50)
    assert res["total"] == 1 and res["items"][0]["lead"]["id"] == solo_id
    assert client.get("/api/stories?ids=abc").status_code == 422
    assert client.get("/api/stories?order=sideways").status_code == 422
    assert stories(ids="999999", limit=50)["total"] == 0


def test_cluster_filter_returns_that_story_only():
    """The cluster filter returns only that story."""
    glacier = glacier_story(stories(limit=50))
    one = stories(cluster=glacier["cluster_id"], limit=50)
    assert one["total"] == 1 and one["article_total"] == 3


def test_flat_articles_endpoint_can_sort_by_information():
    """The flat articles endpoint can sort by information score."""
    items = client.get(f"/api/articles?order=info&limit=50&ids={','.join(map(str, MINE))}").json()["items"]
    scores = [a["info_score"] for a in items]
    assert scores == sorted(scores, reverse=True)
