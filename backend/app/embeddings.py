"""Optional semantic embeddings for story clustering.

Word overlap misses paraphrases ("ground stop" vs "flights halted nationwide"), so when an
OpenAI-compatible ``/embeddings`` endpoint is configured each shared article gets a vector and
:mod:`app.clustering` also links headlines whose meaning is close. Without one, clustering simply
stays lexical: nothing here is required.

Vectors are stored per article as base64 float16 (256 dimensions by default is about 0.7 KB), tagged
with the model that made them so changing models never mixes incompatible vectors. Only shared
articles are embedded; a visitor's own articles are never sent to a paid API.
"""

from __future__ import annotations

import base64
import logging
import struct
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import Article

logger = logging.getLogger("signaldesk.embeddings")

BATCH = 64            # texts per request
PER_WAVE = 256        # articles embedded per backlog wave
WINDOW_DAYS = 4       # embed only what clustering can still use


def available() -> bool:
    """True when embeddings are switched on and an endpoint is reachable by config."""
    if not config.EMBEDDINGS_ENABLED:
        return False
    if config.EMBEDDING_API_KEY:
        return True
    return "api.openai.com" not in config.EMBEDDING_BASE_URL  # local servers need no key


def encode(vector: list[float]) -> str:
    """Pack a vector as base64 float16."""
    return base64.b64encode(struct.pack(f"<{len(vector)}e", *vector)).decode("ascii")


def decode(blob: str) -> np.ndarray:
    """Unpack a stored vector and normalise it, so a dot product is a cosine."""
    raw = base64.b64decode(blob)
    vec = np.array(struct.unpack(f"<{len(raw) // 2}e", raw), dtype=np.float32)
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm else vec


def article_text(a: Article) -> str:
    """What gets embedded: the headline and the start of the summary."""
    return f"{a.title}. {(a.summary or '')[:400]}".strip()


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed `texts` in batches; None when the provider fails or answers unusably (never raises)."""
    headers = {"Content-Type": "application/json"}
    if config.EMBEDDING_API_KEY:
        headers["Authorization"] = f"Bearer {config.EMBEDDING_API_KEY}"
    out: list[list[float]] = []
    for start in range(0, len(texts), BATCH):
        batch = texts[start:start + BATCH]
        payload: dict[str, Any] = {"model": config.EMBEDDING_MODEL, "input": batch}
        if config.EMBEDDING_DIMENSIONS:
            payload["dimensions"] = config.EMBEDDING_DIMENSIONS
        try:
            resp = httpx.post(f"{config.EMBEDDING_BASE_URL}/embeddings", headers=headers, json=payload, timeout=30)
            if resp.status_code == 400 and "dimensions" in payload:
                payload.pop("dimensions")  # models that cannot shorten their vectors reject the parameter
                resp = httpx.post(f"{config.EMBEDDING_BASE_URL}/embeddings", headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            vectors = [[float(x) for x in d["embedding"]] for d in data]
        except Exception as exc:  # noqa: BLE001
            logger.warning("[embeddings] request failed: %s", exc)
            return None
        if len(vectors) != len(batch) or len({len(v) for v in vectors}) != 1 or not vectors[0]:
            logger.warning("[embeddings] unusable response: %s vectors for %s texts", len(vectors), len(batch))
            return None
        out.extend(vectors)
    return out


def embed_pending(db: Session, limit: int = PER_WAVE) -> int:
    """Embed recent shared articles that have no vector for the current model. Returns how many were stored."""
    if not available() or db.info.get("workspace"):
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    articles = db.execute(
        select(Article)
        .where(Article.is_seed.is_(False), Article.workspace_id == "",
               (Article.embedding.is_(None)) | (Article.embedding_model != config.EMBEDDING_MODEL),
               (Article.published_at >= cutoff) | Article.published_at.is_(None))
        .order_by(Article.id.desc()).limit(limit)
    ).scalars().all()
    if not articles:
        return 0
    vectors = embed_texts([article_text(a) for a in articles])
    if vectors is None:
        return 0
    for article, vector in zip(articles, vectors):
        article.embedding, article.embedding_model = encode(vector), config.EMBEDDING_MODEL
    db.commit()
    logger.info("[embeddings] embedded %s articles with %s", len(articles), config.EMBEDDING_MODEL)
    return len(articles)


def vectors_for(rows: list[tuple]) -> dict[int, np.ndarray]:
    """{article id: unit vector} from (id, embedding, model) rows, keeping only the current model's vectors."""
    out: dict[int, np.ndarray] = {}
    for article_id, blob, model in rows:
        if blob and model == config.EMBEDDING_MODEL:
            try:
                out[article_id] = decode(blob)
            except Exception:  # noqa: BLE001
                continue  # a corrupt vector just means that article clusters lexically
    return out
