"""Information score: ranking reports by how much real information they carry."""

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

_test_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_dir}/quality.db"
os.environ["INGEST_INTERVAL_MINUTES"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.analysis import has_boilerplate, strip_boilerplate  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Article  # noqa: E402
from app.quality import MAX_POINTS, backfill_info_scores, breakdown, information_score  # noqa: E402

RICH_BRIEF = (
    "## TL;DR\nSomething happened.\n"
    "## Key points\n- one\n- two\n- three\n- four\n- five\n- six\n"
    "## By the numbers\n- 70 countries were affected.\n"
    "## Notable quotes\n- \"We are deeply sorry,\" the company said.\n"
    "## Bottom line\nResilience matters."
)


def make(**kw):
    """Build an article stand-in with empty fields overridden by `kw`."""
    base = dict(full_text=None, summary=None, summary_deep=None, summary_structured=None, analysis_source=None,
                image_url=None, published_at=None, keywords=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_rich_report_outscores_a_thin_excerpt():
    """A rich report outscores a thin excerpt."""
    rich = make(full_text="word " * 1400, summary_deep="A summary.", summary_structured=RICH_BRIEF,
                analysis_source="lexicon", image_url="https://x/i.jpg", published_at=datetime.now(timezone.utc),
                keywords="a, b, c, d")
    thin = make(summary="Short feed excerpt about the thing.", published_at=datetime.now(timezone.utc))
    assert information_score(rich) > 85
    assert information_score(thin) < 10
    assert information_score(rich) > information_score(thin)


def test_longer_text_scores_higher_until_full_depth():
    """Longer text scores higher until full depth is reached."""
    # Full depth is reached around 6000 characters.
    short = make(full_text="x" * 1500)
    medium = make(full_text="x" * 3000)
    full = make(full_text="x" * 6000)
    over = make(full_text="x" * 20000)
    assert information_score(short) < information_score(medium) < information_score(full)
    assert information_score(full) == information_score(over)  # capped at full depth


def test_no_full_text_can_never_count_as_in_depth():
    """An article without full text never counts as in depth."""
    assert breakdown(make(summary="x" * 5000))["depth"] <= 6


def test_llm_analysis_beats_a_plain_deep_summary():
    """An LLM analysis beats a plain deep summary."""
    llm = make(full_text="x" * 3000, summary_deep="s", analysis_source="llm")
    plain = make(full_text="x" * 3000, summary_deep="s", analysis_source="lexicon")
    assert information_score(llm) > information_score(plain)


def test_substance_counts_numbers_quotes_points_and_conclusion():
    """Substance counts numbers, quotes, key points and a conclusion."""
    parts = breakdown(make(summary_structured=RICH_BRIEF))
    # Numbers + key points + quotes + bottom line.
    assert parts["substance"] == 8 + 6 + 8 + 3


def test_scraped_boilerplate_is_penalised_and_stripped():
    """Scraped boilerplate is penalised and stripped."""
    dirty = "Skip Navigation Markets Business Investing Tech The FAA issued a ground stop on Friday."
    assert has_boilerplate(dirty)
    cleaned = strip_boilerplate(dirty)
    assert not has_boilerplate(cleaned)
    assert "FAA issued a ground stop" in cleaned
    assert breakdown(make(full_text=dirty))["penalty"] == -10
    assert breakdown(make(full_text=cleaned))["penalty"] == 0
    assert "Story text" not in strip_boilerplate("Story text Size Width Links * Subscribers only Learn more It was big.")


def test_score_is_bounded():
    """The score stays within its bounds."""
    assert 0 <= information_score(make()) <= 100
    assert MAX_POINTS == 85


def test_backfill_scores_unscored_rows_and_cleans_boilerplate():
    """The backfill scores unscored rows and cleans boilerplate."""
    Base.metadata.create_all(bind=engine)
    dirty_text = ("Skip Navigation Markets Business Investing Tech The agency announced a nationwide ground stop "
                  "on Friday afternoon after a communications failure, disrupting hundreds of flights across the "
                  "country and stranding thousands of passengers at major airports. " * 6)
    with SessionLocal() as db:
        db.add(Article(title="Dirty piece", url="https://q.example/dirty", source="S", topic="World", sentiment=0.0,
                       full_text=dirty_text, summary_deep="Skip Navigation Markets Business The agency announced",
                       analysis_source="lexicon"))
        db.add(Article(title="Plain piece", url="https://q.example/plain", source="S", topic="World", sentiment=0.0,
                       summary="Just an excerpt."))
        db.commit()
        result = backfill_info_scores(db)
        assert result["cleaned"] >= 1 and result["scored"] >= 2
        dirty = db.query(Article).filter_by(url="https://q.example/dirty").one()
        plain = db.query(Article).filter_by(url="https://q.example/plain").one()
        assert not has_boilerplate(dirty.full_text) and not has_boilerplate(dirty.summary_deep)
        assert dirty.info_score > plain.info_score >= 0
        assert backfill_info_scores(db) == {"cleaned": 0, "scored": 0}  # idempotent
