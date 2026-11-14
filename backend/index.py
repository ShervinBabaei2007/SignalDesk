"""Vercel entrypoint for the backend service: exposes the FastAPI app and prepares the database on cold start."""

from app.main import app, init_database  # noqa: F401

# Vercel may not run the ASGI lifespan, so create/seed the schema here (safe to repeat).
init_database()
