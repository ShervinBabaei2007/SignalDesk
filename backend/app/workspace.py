"""Private workspaces: signed visitor tokens, per-visitor limits, reset and expiry.

A workspace is nothing but an id stamped on the feeds, watches and articles a visitor creates (see
:mod:`app.models`); there is no workspace table. The id travels in a signed, stateless token
(``ws.<id>.<signature>``) sent the same way as the API token, so a visitor can neither guess nor
forge another workspace's id. The shared base data and the owner belong to :data:`NO_WORKSPACE`.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import config
from .models import NO_WORKSPACE, Article, Feed, Watch, WatchAlert

_PREFIX = "ws"


def enabled() -> bool:
    """True when a signing secret is configured, so workspaces can be issued."""
    return bool(config.SESSION_SECRET)


def _sign(payload: str) -> str:
    """Sign a payload with a key derived from the secret, so a workspace token can never be the API token."""
    return hmac.new(f"{config.SESSION_SECRET}:workspace".encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue() -> tuple[str, str]:
    """Create a new workspace; returns (workspace id, signed token)."""
    workspace_id = secrets.token_urlsafe(9)
    payload = f"{_PREFIX}.{workspace_id}"
    return workspace_id, f"{payload}.{_sign(payload)}"


def verify(token: str) -> str | None:
    """The workspace id a token was signed for, or None when it is not a valid workspace token."""
    parts = token.split(".")
    if not enabled() or len(parts) != 3 or parts[0] != _PREFIX or not parts[1]:
        return None
    return parts[1] if hmac.compare_digest(parts[2], _sign(f"{parts[0]}.{parts[1]}")) else None


class RateLimiter:
    """Allow `limit` hits per key in a sliding window. In-memory, so best-effort on serverless: it only
    has to blunt a loop that mints workspaces, not be an exact quota."""

    def __init__(self, limit: int, window_seconds: float = 3600.0):
        self.limit, self.window = limit, window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        """Record a hit for `key`; False when it already used up its allowance."""
        now = time.time() if now is None else now
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if now - t < self.window]
            allowed = len(recent) < self.limit
            if allowed:
                recent.append(now)
            self._hits[key] = recent
            if len(self._hits) > 5000:  # keep memory bounded
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window}
            return allowed


creations = RateLimiter(config.WORKSPACE_CREATES_PER_HOUR)


def count(db: Session, model, workspace_id: str) -> int:
    """How many rows of `model` the workspace owns."""
    return db.scalar(select(func.count()).select_from(model).where(model.workspace_id == workspace_id)) or 0


def reset(db: Session, workspace_id: str) -> None:
    """Delete everything a workspace owns. The shared base data is never touched."""
    if workspace_id == NO_WORKSPACE:
        return
    watches = Watch.__table__  # core table: the ORM's workspace scoping must not hide rows from a cleanup
    watch_ids = [w for (w,) in db.execute(select(watches.c.id).where(watches.c.workspace_id == workspace_id)).all()]
    if watch_ids:
        db.execute(delete(WatchAlert).where(WatchAlert.watch_id.in_(watch_ids)))
    for model in (Watch, Feed, Article):
        db.execute(delete(model).where(model.workspace_id == workspace_id))
    db.commit()


def purge_expired(db: Session, now: datetime | None = None) -> int:
    """Delete workspace rows older than WORKSPACE_TTL_DAYS (called from the cron). Returns rows removed."""
    if config.WORKSPACE_TTL_DAYS <= 0:
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=config.WORKSPACE_TTL_DAYS)
    removed = 0
    watches = Watch.__table__  # core table: a cleanup session must see every workspace's rows
    stale_watches = [w for (w,) in db.execute(
        select(watches.c.id).where(watches.c.workspace_id != NO_WORKSPACE, watches.c.created_at < cutoff)).all()]
    if stale_watches:
        db.execute(delete(WatchAlert).where(WatchAlert.watch_id.in_(stale_watches)))
        removed += db.execute(delete(Watch).where(Watch.id.in_(stale_watches))).rowcount or 0
    for model, column in ((Feed, Feed.created_at), (Article, Article.ingested_at)):
        removed += db.execute(delete(model).where(model.workspace_id != NO_WORKSPACE, column < cutoff)).rowcount or 0
    db.commit()
    return removed
