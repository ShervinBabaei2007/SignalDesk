"""Database engine and session management for SignalDesk.

Uses SQLite by default (zero-config, perfect for demos) and can be pointed
at PostgreSQL via the DATABASE_URL environment variable for production.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


def _normalize_url(url: str) -> str:
    """Point bare postgres:// and postgresql:// URLs (as Neon and Vercel give them) at the psycopg 3 driver."""
    # Swap whichever bare scheme the URL uses for the explicit psycopg 3 dialect.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _normalize_url(os.getenv("DATABASE_URL", "").strip()) or f"sqlite:///{BASE_DIR / 'signaldesk.db'}"
# SQLite connections are shared across FastAPI's worker threads, so its same-thread check is disabled.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base class shared by all ORM models."""


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columns that used to be globally unique and are now unique per workspace.
_LEGACY_UNIQUE = {"articles": ["url"], "feeds": ["name", "url"]}


def _legacy_uniques(inspector) -> list[tuple[str, str, str | None, str]]:
    """(table, 'constraint' | 'index', name, column) for each old single-column unique that must go."""
    found = []
    tables = set(inspector.get_table_names())
    # Check each table that used to carry a global unique for the old single-column uniques.
    for table, columns in _LEGACY_UNIQUE.items():
        if table not in tables:
            continue
        if inspector.dialect.name == "sqlite":
            # SQLAlchemy's SQLite inspector misses column-level UNIQUE, so read the unique indexes directly.
            with inspector.bind.connect() as conn:
                for row in conn.execute(text(f"PRAGMA index_list({table})")).mappings():
                    if not row["unique"]:
                        continue
                    cols = [r["name"] for r in conn.execute(text(f'PRAGMA index_info("{row["name"]}")')).mappings()]
                    if len(cols) == 1 and cols[0] in columns:
                        # sqlite_autoindex_* backs an inline UNIQUE constraint; anything else is a named index.
                        found.append((table, "constraint" if row["name"].startswith("sqlite_autoindex") else "index",
                                      row["name"], cols[0]))
            continue
        # Other dialects report constraints and unique indexes separately; collect both kinds.
        for uc in inspector.get_unique_constraints(table):
            if len(uc["column_names"]) == 1 and uc["column_names"][0] in columns:
                found.append((table, "constraint", uc.get("name"), uc["column_names"][0]))
        for ix in inspector.get_indexes(table):
            if (ix.get("unique") and not ix.get("duplicates_constraint")
                    and len(ix["column_names"]) == 1 and ix["column_names"][0] in columns):
                found.append((table, "index", ix["name"], ix["column_names"][0]))
    return found


def _rebuild_sqlite_tables(tables: set[str]) -> None:
    """SQLite cannot drop a UNIQUE constraint, so recreate each table from the models and copy its rows."""
    with engine.begin() as conn:
        # Rename each old table aside, create the new one from the model, copy the shared columns, drop the old.
        for table in sorted(tables):
            conn.execute(text(f"ALTER TABLE {table} RENAME TO {table}_legacy"))
            # Drop the old named indexes so the new table can reuse their names.
            for ix in inspect(conn).get_indexes(f"{table}_legacy"):
                if ix["name"] and not ix["name"].startswith("sqlite_autoindex"):
                    conn.execute(text(f'DROP INDEX IF EXISTS "{ix["name"]}"'))
            Base.metadata.tables[table].create(conn)
            old = {c["name"] for c in inspect(conn).get_columns(f"{table}_legacy")}
            cols = ", ".join(c.name for c in Base.metadata.tables[table].columns if c.name in old)
            conn.execute(text(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM {table}_legacy"))
            conn.execute(text(f"DROP TABLE {table}_legacy"))


def migrate_workspace_uniques() -> None:
    """Make article URLs and feed names/URLs unique per workspace instead of globally.

    Idempotent. Run before the new columns are added on SQLite (the tables are rebuilt) and after on
    PostgreSQL (the old constraints are dropped and composite unique indexes created).
    """
    legacy = _legacy_uniques(inspect(engine))
    if engine.dialect.name == "sqlite":
        if legacy:
            _rebuild_sqlite_tables({table for table, *_ in legacy})
        return
    with engine.begin() as conn:
        # Drop each legacy unique by its kind; unnamed ones cannot be addressed and are skipped.
        for table, kind, name, _ in legacy:
            if name:
                conn.execute(text(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{name}"') if kind == "constraint"
                             else text(f'DROP INDEX IF EXISTS "{name}"'))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_articles_url ON articles (url)"))
        # Recreate uniqueness as composite (workspace_id, column) indexes matching the models.
        for table, ddl in (("articles", "uq_article_workspace_url ON articles (workspace_id, url)"),
                           ("feeds", "uq_feed_workspace_name ON feeds (workspace_id, name)"),
                           ("feeds", "uq_feed_workspace_url ON feeds (workspace_id, url)")):
            conn.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {ddl}"))


def ensure_columns():
    """Add columns that were introduced after a table already exists.

    create_all() only creates missing *tables*, so columns added later need
    explicit ALTER TABLE statements. Idempotent: inspects before altering.
    """
    if engine.dialect.name == "sqlite":
        migrate_workspace_uniques()  # rebuilds legacy tables before their columns are inspected below
    inspector = inspect(engine)
    migrations = {
        "articles": {
            "keywords": "VARCHAR(500)",
            "image_url": "VARCHAR(1000)",
            "info_score": "FLOAT",
            "summary_deep": "TEXT",
            "summary_structured": "TEXT",
            "full_text": "TEXT",
            "enriched_at": "TIMESTAMP WITH TIME ZONE",
            "why_it_matters": "TEXT",
            "importance": "FLOAT",
            "relevance": "FLOAT",
            "content_type": "VARCHAR(40)",
            "analysis_model": "VARCHAR(100)",
            "analysis_source": "VARCHAR(20)",
            "extraction": "VARCHAR(12)",
            "signals": "TEXT",
            "embedding": "TEXT",
            "embedding_model": "VARCHAR(80)",
        },
        "feeds": {"last_fetched_at": "TIMESTAMP WITH TIME ZONE", "last_status": "VARCHAR(300)"},
        "story_briefs": {"claims": "TEXT"},
    }
    # Every workspace-scoped table gets a workspace_id column defaulting to the shared data.
    for table in ("articles", "feeds", "watches"):
        migrations.setdefault(table, {})["workspace_id"] = "VARCHAR(40) NOT NULL DEFAULT ''"
    # Add each missing column to tables that already exist.
    for table, columns in migrations.items():
        if table not in inspector.get_table_names():
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for column, col_type in columns.items():
            if column not in existing:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
    if engine.dialect.name != "sqlite":
        migrate_workspace_uniques()
    # Index workspace_id on every scoped table, since each query filters on it.
    for table in ("articles", "feeds", "watches"):
        if table in inspect(engine).get_table_names():
            with engine.begin() as conn:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_workspace_id ON {table} (workspace_id)"))
