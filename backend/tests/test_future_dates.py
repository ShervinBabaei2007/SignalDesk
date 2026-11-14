"""Future-dated articles must not reach the sentiment trend."""
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import ingestion, reporting
from app.database import Base
from app.models import Article


@pytest.fixture()
def db():
    """In-memory database."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as session:
        yield session


def test_clamp_future_replaces_far_future_dates():
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert ingestion.clamp_future(now + timedelta(days=1), now) == now
    assert ingestion.clamp_future(now + timedelta(minutes=30), now) == now + timedelta(minutes=30)
    assert ingestion.clamp_future(now - timedelta(days=2), now) == now - timedelta(days=2)
    assert ingestion.clamp_future(None, now) is None


def test_parse_published_treats_feed_time_as_utc():
    entry = type("E", (), {"published_parsed": time.struct_time((2026, 1, 1, 23, 30, 0, 3, 1, 0))})()
    assert ingestion._parse_published(entry) == datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc)


def test_trend_excludes_future_articles(db):
    now = datetime.now(timezone.utc)
    for i, when in enumerate([now - timedelta(days=1), now + timedelta(days=2)]):
        db.add(Article(title=f"t{i}", url=f"https://x.test/{i}", source="s", topic="World",
                       sentiment=0.1, published_at=when, is_seed=False))
    db.commit()
    days = [p["date"] for p in reporting.stats(db).sentiment_7d]
    assert (now + timedelta(days=2)).strftime("%Y-%m-%d") not in days
    assert (now - timedelta(days=1)).strftime("%Y-%m-%d") in days
