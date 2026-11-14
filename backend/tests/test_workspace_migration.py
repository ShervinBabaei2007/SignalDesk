"""The schema migration that makes feeds and article URLs unique per workspace."""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app import database, models  # noqa: F401  (models register their tables on Base)

LEGACY_SCHEMA = """
CREATE TABLE feeds (id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL UNIQUE, url VARCHAR(1000) NOT NULL UNIQUE,
  is_active BOOLEAN, created_at DATETIME, last_fetched_at DATETIME, last_status VARCHAR(300));
CREATE TABLE articles (id INTEGER PRIMARY KEY, title VARCHAR(500) NOT NULL, url VARCHAR(1000) NOT NULL,
  source VARCHAR(200) NOT NULL, topic VARCHAR(50), sentiment FLOAT, ingested_at DATETIME, is_seed BOOLEAN);
CREATE UNIQUE INDEX ix_articles_url ON articles (url);
CREATE TABLE watches (id INTEGER PRIMARY KEY, term VARCHAR(100) NOT NULL, topic VARCHAR(50), min_outlets INTEGER,
  is_active BOOLEAN, created_at DATETIME);
INSERT INTO feeds (id, name, url, is_active, created_at) VALUES (1, 'BBC', 'https://bbc.test/rss', 1, '2026-01-01');
INSERT INTO articles (id, title, url, source, topic, sentiment, ingested_at, is_seed) VALUES (1, 'Old story', 'https://x.test/1', 'BBC', 'World', 0.1, '2026-01-01', 0);
INSERT INTO watches (id, term, min_outlets, is_active, created_at) VALUES (1, 'chips', 2, 1, '2026-01-01');
"""


@pytest.fixture()
def legacy_engine(monkeypatch):
    """An in-memory SQLite database in the pre-workspace shape, wired in as the app's engine."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:
        # SQLAlchemy runs one statement at a time, so split the script on statement ends.
        for statement in LEGACY_SCHEMA.strip().split(";\n"):
            conn.execute(text(statement))
    monkeypatch.setattr(database, "engine", engine)
    return engine


def test_migration_keeps_rows_and_allows_the_same_feed_in_two_workspaces(legacy_engine):
    """Existing rows land in the shared workspace, and uniqueness now applies per workspace."""
    database.ensure_columns()
    with legacy_engine.begin() as conn:
        assert conn.execute(text("SELECT workspace_id, name FROM feeds")).all() == [("", "BBC")]
        assert conn.execute(text("SELECT title, workspace_id FROM articles")).all() == [("Old story", "")]
        assert conn.execute(text("SELECT term, workspace_id FROM watches")).all() == [("chips", "")]
        # the same feed and article URL in another workspace no longer collides
        conn.execute(text("INSERT INTO feeds (name, url, workspace_id, is_active, created_at) VALUES ('BBC', 'https://bbc.test/rss', 'u1', 1, '2026-01-01')"))
        conn.execute(text("INSERT INTO articles (title, url, source, topic, sentiment, is_seed, workspace_id, ingested_at) "
                          "VALUES ('Mine', 'https://x.test/1', 'BBC', 'World', 0, 0, 'u1', '2026-01-01')"))
    with pytest.raises(Exception):  # but within one workspace they are still unique
        with legacy_engine.begin() as conn:
            conn.execute(text("INSERT INTO feeds (name, url, workspace_id, is_active, created_at) VALUES ('BBC', 'https://other.test', '', 1, '2026-01-01')"))


def test_migration_is_idempotent(legacy_engine):
    """Running the migration twice leaves the workspace column and no legacy unique constraints."""
    database.ensure_columns()
    database.ensure_columns()
    inspector = inspect(legacy_engine)
    assert {c["name"] for c in inspector.get_columns("feeds")} >= {"workspace_id"}
    assert database._legacy_uniques(inspector) == []
