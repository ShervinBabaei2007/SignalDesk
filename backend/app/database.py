"""Database engine and session management for SignalDesk.

Uses SQLite by default (zero-config, perfect for demos) and can be pointed
at PostgreSQL via the DATABASE_URL environment variable for production.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/

_database_url = os.getenv("DATABASE_URL", "").strip()
if _database_url:
    DATABASE_URL = _database_url
else:
    DATABASE_URL = f"sqlite:///{BASE_DIR / 'signaldesk.db'}"
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_columns():
    """Add columns that were introduced after a table already exists.

    create_all() only creates missing *tables*, so columns added later need
    explicit ALTER TABLE statements. Idempotent: inspects before altering.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    migrations = {
        "articles": {"keywords": "VARCHAR(500)"},
        "feeds": {"last_fetched_at": "TIMESTAMP WITH TIME ZONE", "last_status": "VARCHAR(300)"},
    }
    for table, columns in migrations.items():
        if table not in inspector.get_table_names():
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for column, col_type in columns.items():
            if column not in existing:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
