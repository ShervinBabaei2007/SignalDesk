"""Vercel entrypoint: exposes the FastAPI app and prepares the database on each cold start."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app, init_database  # noqa: E402

# Vercel may not run the ASGI lifespan, so create/seed the schema here (safe to repeat).
init_database()
