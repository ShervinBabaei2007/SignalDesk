"""Database engine and session management for SignalDesk.

Uses SQLite by default (zero-config, perfect for demos) and can be pointed
at PostgreSQL via the DATABASE_URL environment variable for production.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/

_database_url = os.getenv("DATABASE_URL", "")
if _database_url.startswith("postgres"):
    DATABASE_URL = _database_url
    connect_args = {}
else:
    DATABASE_URL = f"sqlite:///{BASE_DIR / 'signaldesk.db'}"
    connect_args = {"check_same_thread": False}

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
