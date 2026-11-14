"""Centralized runtime configuration for SignalDesk.

Every knob is environment-driven so the same image can run unmodified in
development, CI, and production. Values are read from the process environment
and, when present, from a `.env` file at the repository root. See
`.env.example` for a documented template.
"""

import os
from pathlib import Path

# Load .env once, without overriding variables that CI/deployments set
# explicitly (load_dotenv is a no-op when python-dotenv isn't installed).
try:  # pragma: no cover - trivial import guard
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass


def _bool(name: str, default: str = "false") -> bool:
    """Read a boolean environment variable."""
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back to the default when unset or invalid."""
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    """Read a float environment variable, falling back to the default when unset or invalid."""
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _csv(name: str, default: str = "") -> list[str]:
    """Read a comma-separated environment variable as a list of trimmed values."""
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()  # development | production
VERSION = "2.2.0"

# Comma-separated list. "*" opens the API to any origin (fine for local dev;
# set explicit origins in production, e.g. "https://dash.example.com").
CORS_ORIGINS = _csv("CORS_ORIGINS", "*")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()

INGEST_INTERVAL_MINUTES = _int("INGEST_INTERVAL_MINUTES", 15)
INGEST_COOLDOWN_SECONDS = _int("INGEST_COOLDOWN_SECONDS", 20)  # min seconds between manual ingests
ENRICH_BATCH_SIZE = _int("ENRICH_BATCH_SIZE", 30)

# Only ingest stories published within this many days (0 disables the filter).
MAX_ARTICLE_AGE_DAYS = _int("MAX_ARTICLE_AGE_DAYS", 7)

SCHEDULER_DISABLED = _bool("SCHEDULER_DISABLED")

# --------------------------------------------------------------------------- #
# Optional LLM analysis (any OpenAI-compatible endpoint: OpenAI, Ollama,
# LM Studio, vLLM, OpenRouter, …). Off by default: the deterministic analyzer
# always works, and the LLM simply upgrades summaries when configured.
# --------------------------------------------------------------------------- #

LLM_ENABLED = _bool("LLM_ENABLED")
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
LLM_TIMEOUT = _int("LLM_TIMEOUT", 45)
LLM_MAX_INPUT_CHARS = _int("LLM_MAX_INPUT_CHARS", 12000)

# --------------------------------------------------------------------------- #
# Digest delivery (Slack incoming webhook and/or SMTP email)
# --------------------------------------------------------------------------- #

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()
DIGEST_EMAILS = _csv("DIGEST_EMAILS")
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = _int("SMTP_PORT", 587)
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER).strip()
SMTP_TLS = _bool("SMTP_TLS", "true")

# UTC hour (0-23) at which the daily brief is delivered automatically.
# -1 disables scheduled delivery. Manual delivery is always available from
# the dashboard / POST /api/digest/send.
DIGEST_HOUR = _int("DIGEST_HOUR", -1)

# --------------------------------------------------------------------------- #
# Optional API-key protection for mutating endpoints. When set, POST/DELETE
# requests must send `X-API-Key: <token>` (or `Authorization: Bearer <token>`).
# --------------------------------------------------------------------------- #

API_TOKEN = os.getenv("API_TOKEN", "").strip()

# Shared secret that Vercel Cron sends as a Bearer token to /api/cron/ingest.
CRON_SECRET = os.getenv("CRON_SECRET", "").strip()
