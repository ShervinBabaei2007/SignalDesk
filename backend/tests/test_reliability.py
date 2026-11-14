"""Source reliability: page transparency signals and explainable outlet profiles."""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_test_dir = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_test_dir}/test.db")
os.environ["INGEST_INTERVAL_MINUTES"] = "0"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import briefs, claims, enrichment, reliability, signals, story_index  # noqa: E402
from app.database import Base, SessionLocal, engine as app_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Article, FeedRun, StoryBrief  # noqa: E402

NOW = datetime.now(timezone.utc)

GOOD_PAGE = """
<html><head>
<meta name="author" content="Jane Reporter">
<meta property="article:published_time" content="2026-01-05T09:00:00Z">
<meta property="article:modified_time" content="2026-01-05T15:30:00Z">
</head><body>
<nav><a href="/corrections">Corrections</a></nav>
<article><p>Officials cited a <a href="https://www.reuters.com/world/report">Reuters report</a> and
<a href="https://data.gov/stats">government data</a>, plus <a href="https://twitter.com/x/status/1">a tweet</a>
and <a href="https://news.example.com/other">our own earlier story</a>.</p>
<p>Correction: an earlier headline misstated the figure.</p></article>
</body></html>
"""


# --------------------------------------------------------------------------- #
# Page signals
# --------------------------------------------------------------------------- #

def test_a_transparent_page_shows_every_signal():
    """A page with byline, dates, external links, a corrections policy and a notice reports every signal."""
    s = signals.extract_signals(GOOD_PAGE, "https://news.example.com/a", "Body\nCorrection: an earlier headline misstated it.")
    assert s == {"byline": True, "published": True, "updated": True, "sources": 2, "policy": True, "correction": True}


def test_signals_are_found_even_when_megabytes_of_script_come_first():
    """Regression: CNBC-style pages put ~600 KB of inline script before the meta tags."""
    padding = "<script>" + "var data = {};" * 60_000 + "</script>"  # ~840 KB
    html = ("<html><head><meta property=\"og:type\" content=\"article\"/>" + padding +
            "<meta name=\"author\" content=\"Jane Reporter\"/>"
            "<meta property=\"article:published_time\" content=\"2026-01-05T09:00:00Z\"/></head><body></body></html>")
    assert len(html) > 600_000
    s = signals.extract_signals(html, "https://news.example.com/a")
    assert s["byline"] and s["published"]


def test_a_bare_page_shows_none():
    """A page with only plain text reports no transparency signals."""
    s = signals.extract_signals("<html><body><p>Just text.</p></body></html>", "https://x.test/a", "Just text.")
    assert s == {"byline": False, "published": False, "updated": False, "sources": 0, "policy": False, "correction": False}


def test_own_domain_and_social_links_do_not_count_as_sourcing():
    """Links to the outlet's own site or social networks are not external sources, but another outlet is."""
    html = ('<p><a href="https://www.news.example.com/x">us</a> <a href="https://facebook.com/s">fb</a> '
            '<a href="https://t.co/abc">t</a></p>')
    assert signals.extract_signals(html, "https://news.example.com/a")["sources"] == 0
    assert signals.extract_signals('<p><a href="https://bbc.co.uk/x">bbc</a></p>', "https://news.example.com/a")["sources"] == 1


def test_bylines_and_dates_are_found_in_json_ld_and_markup():
    """Bylines and dates are detected from JSON-LD as well as byline classes and time tags."""
    ld = '<script type="application/ld+json">{"author": {"name": "A"}, "datePublished": "2026-01-01", "dateModified": "2026-01-01"}</script>'
    s = signals.extract_signals(f"<html><head>{ld}</head><body></body></html>")
    assert s["byline"] and s["published"] and not s["updated"]  # modified equals published: not an update
    s = signals.extract_signals('<div class="article-byline">By Sam</div><time datetime="2026-01-01">Jan 1</time>')
    assert s["byline"] and s["published"]


@pytest.mark.parametrize("text,expected", [
    ("Correction: the minister's name was misspelt.", True),
    ("Clarification - this story was updated.", True),
    ("An earlier version of this article said 5%.", True),
    ("The company said the correction in prices was overdue.", False),
    ("", False),
])
def test_correction_notices_are_told_from_the_word_correction(text, expected):
    """Real correction or clarification notices are detected, while ordinary uses of "correction" are not."""
    assert signals.has_correction_notice(text) is expected


def test_enrichment_stores_the_signals_it_finds(monkeypatch):
    """Fetching a page returns its text together with the transparency signals found on it."""
    class Resp:
        """Fake HTTP response serving the transparent page padded with enough article text to extract."""
        status_code, headers, url = 200, {"content-type": "text/html"}, "https://news.example.com/a"
        text = GOOD_PAGE.replace("<article>", "<article>" + "<p>" + "A long sentence about the economy. " * 12 + "</p>")
    monkeypatch.setattr(enrichment.httpx, "get", lambda *a, **k: Resp())
    text, image, found = enrichment.fetch_page_signals("https://news.example.com/a")
    assert text and found["byline"] and found["sources"] == 2
    assert enrichment.fetch_page("https://news.example.com/a")[0] == text  # the two-value wrapper still works


# --------------------------------------------------------------------------- #
# Profiles
# --------------------------------------------------------------------------- #

@pytest.fixture()
def db():
    """In-memory database; the profile cache is cleared around each test."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    reliability.reset_cache()
    with sessionmaker(bind=engine)() as session:
        yield session
    reliability.reset_cache()


FULL = {"byline": True, "published": True, "updated": False, "sources": 2, "policy": True, "correction": False}
NONE = {"byline": False, "published": False, "updated": False, "sources": 0, "policy": False, "correction": False}


def seed(db, source, n, *, signals_=FULL, info=80.0, start=1, workspace="", title=None):
    """Add `n` reports for `source` (ids from `start`); `title(i)` can make outlets share a headline."""
    # Every report is a day old so it sits inside the profile window.
    for i in range(start, start + n):
        db.add(Article(id=i, title=title(i) if title else f"{source} story {i}", url=f"https://{source}.test/{i}", source=source, topic="World",
                       sentiment=0.0, is_seed=False, info_score=info, workspace_id=workspace,
                       signals=json.dumps(signals_) if signals_ is not None else None,
                       published_at=NOW - timedelta(days=1), ingested_at=NOW - timedelta(days=1)))
    db.commit()
    story_index.reset_cache()


DISTINCT = ["volcano", "earthquake", "election", "merger", "strike", "drought"]


def shared_event(k):
    """A headline with its own vocabulary, so two outlets using it cover one event and nothing else matches it."""
    return f"{DISTINCT[k]} alpha{k}x bravo{k}y charlie{k}z delta{k}w"


def test_a_well_evidenced_outlet_gets_an_explained_score_rescaled_over_what_is_known(db):
    """A well-evidenced outlet gets per-part points and a score rescaled over only the parts that are known."""
    # half of Alpha's reports are about events that Beta also covers (same headline), the rest are its own
    seed(db, "Alpha", 12, title=lambda i: shared_event(i - 1) if i <= 6 else f"unique{i}a unique{i}b unique{i}c")
    seed(db, "Beta", 6, start=100, title=lambda i: shared_event(i - 100))
    # Twelve successful hourly fetches give Alpha full availability points.
    db.add_all([FeedRun(run_id=1, feed="Alpha", at=NOW - timedelta(hours=h), ok=True) for h in range(12)])
    db.commit()
    p = reliability.compute(db, NOW)["Alpha"]
    parts = {c["key"]: c for c in p["breakdown"]}
    assert parts["transparency"]["points"] == 30 and parts["corrections"]["points"] == 10
    assert parts["information"]["points"] == 16.0 and parts["corroboration"]["points"] == 20.0
    assert parts["availability"]["points"] == 10 and parts["agreement"]["points"] is None
    assert p["score"] == round(100 * 86 / 90) and p["label"] == "Strong signals"  # agreement is left out, not counted as zero
    assert "12 recent reports" in parts["corroboration"]["detail"]
    assert "Only 0 compared claims" in parts["agreement"]["detail"]
    assert p["corroboration_rate"] == 0.5 and p["first_report_rate"] is not None  # judged from live clusters, no events needed


def test_an_opaque_low_information_outlet_gets_limited_signals(db):
    """An outlet with no page signals and thin reports scores below the mixed band."""
    seed(db, "Opaque", 12, signals_=NONE, info=20.0)
    p = reliability.compute(db, NOW)["Opaque"]
    assert p["score"] is not None and p["score"] < reliability.MIXED and p["label"] == "Limited signals"
    assert next(c for c in p["breakdown"] if c["key"] == "corrections")["points"] == 0  # no corrections practice


def test_too_little_evidence_withholds_the_score_instead_of_guessing(db):
    """An outlet with only a few reports gets no score and no part points."""
    seed(db, "Thin", 3)
    p = reliability.compute(db, NOW)["Thin"]
    assert p["score"] is None and p["label"] == "Not enough data" and p["articles"] == 3
    assert all(c["points"] is None for c in p["breakdown"])


def test_without_page_signals_the_score_is_withheld_however_many_reports_there_are(db):
    """Many reports but no page signals still withholds the overall score while showing the parts."""
    seed(db, "NoPages", 30, signals_=None)  # information and corroboration alone are only 40 of 100: too thin to score
    p = reliability.compute(db, NOW)["NoPages"]
    assert p["score"] is None and p["label"] == "Not enough data" and p["articles"] == 30
    assert next(c for c in p["breakdown"] if c["key"] == "information")["points"] is not None  # the parts are still shown


def test_corroboration_ignores_stories_older_than_the_window(db):
    """Matching reports from another outlet that are too old do not count as corroboration."""
    seed(db, "Alpha", 12, title=lambda i: shared_event(i % 6))
    seed(db, "Beta", 6, start=100, title=lambda i: shared_event(i - 100))
    old = NOW - timedelta(days=10)
    for a in db.execute(select(Article).where(Article.source == "Beta")).scalars():
        a.published_at = old  # Beta's matching reports are too old to count as the same event
    db.commit()
    story_index.reset_cache()
    assert reliability.compute(db, NOW)["Alpha"]["corroboration_rate"] == 0.0


def test_many_correction_notices_count_against_an_outlet(db):
    """An outlet correcting every report loses correction points compared with a careful one."""
    noisy = dict(FULL, correction=True)
    seed(db, "Noisy", 12, signals_=noisy)
    seed(db, "Careful", 12, start=100)
    profiles = reliability.compute(db, NOW)
    pts = lambda name: next(c for c in profiles[name]["breakdown"] if c["key"] == "corrections")["points"]  # noqa: E731
    assert pts("Noisy") < pts("Careful") == 10
    assert profiles["Noisy"]["corrections"] == {"notices": 12, "rate": 1.0, "policy": True}


def test_agreement_uses_cached_claims_of_shared_stories_only(db):
    """Agreement points come from cached claims of shared stories, never from visitor stories."""
    seed(db, "Alpha", 12)
    seed(db, "Visitor stuff", 12, start=500, workspace="visitor")
    # Four agreed and two disputed claims, so Alpha agrees on 4 of 6.
    items = [{"status": "agreed", "outlets": ["Alpha", "Beta"]}] * 4 + [{"status": "disputed", "outlets": ["Alpha", "Beta"]}] * 2
    db.add(StoryBrief(cluster_id=1, member_hash="h", payload="{}", claims=json.dumps({"kind": "auto", "items": items})))
    db.add(StoryBrief(cluster_id=500, member_hash="h", payload="{}", claims=json.dumps({"kind": "auto", "items": items})))
    db.commit()
    profiles = reliability.compute(db, NOW)
    agreement = next(c for c in profiles["Alpha"]["breakdown"] if c["key"] == "agreement")
    assert agreement["points"] == round(10 * 4 / 6, 1) and "4 of 6" in agreement["detail"]
    assert "Visitor stuff" not in profiles  # a visitor's articles and stories never feed a public profile


def test_a_visitor_session_cannot_change_a_public_profile(db):
    """A visitor's own low-quality reports under a public outlet's name leave that outlet's profile unchanged."""
    seed(db, "Alpha", 12)
    before = reliability.compute(db, NOW)["Alpha"]
    seed(db, "Alpha", 20, start=700, workspace="visitor", signals_=NONE, info=1.0)
    db.info["workspace"] = "visitor"
    assert reliability.compute(db, NOW)["Alpha"] == before


def test_profiles_are_cached_briefly(db, monkeypatch):
    """Profiles are served from cache until the cache is reset."""
    seed(db, "Alpha", 12)
    first = reliability.profiles(db)
    seed(db, "Gamma", 12, start=900)
    assert reliability.profiles(db) is first  # served from the cache
    reliability.reset_cache()
    assert "Gamma" in reliability.profiles(db)


def test_listing_orders_best_first_with_the_disclaimer(db):
    """The source listing ranks scored outlets by score, puts unscored ones last and carries the disclaimer."""
    seed(db, "Alpha", 12)
    seed(db, "Opaque", 12, start=100, signals_=NONE, info=20.0)
    seed(db, "Thin", 2, start=200)
    out = reliability.listing(db)
    assert [p["source"] for p in out["items"]] == ["Alpha", "Opaque", "Thin"]
    assert "not an editorial rating" in out["note"] and out["window_days"] == 30


# --------------------------------------------------------------------------- #
# Cache isolation: a visitor's article must not leak through a shared cache
# --------------------------------------------------------------------------- #

def members(db, workspace_for_second=""):
    """Two reports, the second optionally a visitor's own."""
    seed(db, "Alpha", 1, start=1)
    seed(db, "Beta", 1, start=2, workspace=workspace_for_second)
    db.info["workspace"] = workspace_for_second
    return db.execute(select(Article).order_by(Article.id)).scalars().all()


def test_a_story_with_a_visitors_article_is_never_cached_for_others(db):
    """Briefs and claims for a story containing a visitor's article are not written to the shared cache."""
    story = members(db, "visitor")
    briefs.get_brief(db, 1, "t", story)
    claims.get_claims(db, 1, "t", story)
    assert db.execute(select(StoryBrief)).first() is None


def test_a_fully_shared_story_is_cached(db):
    """Briefs and claims for a story of only shared articles are cached."""
    story = members(db, "")
    briefs.get_brief(db, 1, "t", story)
    claims.get_claims(db, 1, "t", story)
    row = db.execute(select(StoryBrief)).scalar_one()
    assert row.claims is not None


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #

def test_the_sources_endpoint_and_story_comparison_expose_reliability():
    """The sources endpoint lists profiles and story comparison shows each outlet's reliability."""
    Base.metadata.create_all(bind=app_engine)
    reliability.reset_cache()
    recent = NOW - timedelta(hours=1)
    with SessionLocal() as session:
        seed(session, "ApiAlpha", 12, start=9200)
        # One story covered by the scored outlet and an outlet with too little data.
        for i, source in ((9301, "ApiAlpha"), (9302, "ApiBeta")):
            session.add(Article(id=i, title="Dam collapse floods valley as thousands flee", url=f"https://x.test/{i}",
                                source=source, topic="World", sentiment=0.0, is_seed=False, published_at=recent))
        session.commit()
    story_index.reset_cache()
    try:
        client = TestClient(app)
        body = client.get("/api/sources").json()
        alpha = next(p for p in body["items"] if p["source"] == "ApiAlpha")
        assert alpha["score"] is not None and len(alpha["breakdown"]) == 6 and "editorial rating" in body["note"]
        comparison = client.get("/api/stories/9301").json()["comparison"]
        by_source = {c["source"]: c for c in comparison}
        assert by_source["ApiAlpha"]["reliability"] == alpha["score"]
        assert by_source["ApiBeta"]["reliability"] is None and by_source["ApiBeta"]["reliability_label"] == "Not enough data"
    finally:
        with SessionLocal() as session:
            session.query(StoryBrief).filter(StoryBrief.cluster_id == 9301).delete()
            session.query(Article).filter(Article.id.in_([*range(9200, 9212), 9301, 9302])).delete(synchronize_session=False)
            session.commit()
        story_index.reset_cache()
        reliability.reset_cache()
