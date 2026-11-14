"""Semantic embeddings: the provider client, storage, and clustering by meaning."""

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import config, embeddings, story_index  # noqa: E402
from app.clustering import MAX_CLUSTER, cluster_rows  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import Article  # noqa: E402

NOW = datetime.now(timezone.utc)


def unit(*xs):
    """A unit-length vector."""
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def rows(titles, hours=1.0):
    """Clustering rows (id, title, source, published) spaced `hours` apart."""
    return [(i + 1, t, f"Src{i}", NOW - timedelta(hours=hours * i)) for i, t in enumerate(titles)]


@pytest.fixture(autouse=True)
def provider(monkeypatch):
    """Switch embeddings on against a made-up endpoint for every test."""
    monkeypatch.setattr(config, "EMBEDDINGS_ENABLED", True)
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "test-embed")
    monkeypatch.setattr(config, "EMBEDDING_BASE_URL", "https://embed.example/v1")
    monkeypatch.setattr(config, "EMBEDDING_API_KEY", "key")
    monkeypatch.setattr(config, "EMBEDDING_DIMENSIONS", 4)
    monkeypatch.setattr(config, "EMBED_SIM_MIN", 0.78)


# --------------------------------------------------------------------------- #
# Storage and the provider client
# --------------------------------------------------------------------------- #

def test_vectors_round_trip_and_come_back_unit_length():
    """Encoded vectors decode normalised to length 1 and are stored compactly."""
    blob = embeddings.encode([3.0, 4.0, 0.0])
    vec = embeddings.decode(blob)
    assert math.isclose(float(np.linalg.norm(vec)), 1.0, rel_tol=1e-3)
    assert math.isclose(float(vec[0]), 0.6, abs_tol=1e-3) and math.isclose(float(vec[1]), 0.8, abs_tol=1e-3)
    assert len(blob) < 20  # base64 float16, not JSON text


def test_availability_needs_opt_in_and_a_key_or_a_local_server(monkeypatch):
    """Embeddings run only when enabled and either a key is set or the endpoint is local."""
    assert embeddings.available()
    monkeypatch.setattr(config, "EMBEDDINGS_ENABLED", False)
    assert not embeddings.available()
    monkeypatch.setattr(config, "EMBEDDINGS_ENABLED", True)
    monkeypatch.setattr(config, "EMBEDDING_API_KEY", "")
    monkeypatch.setattr(config, "EMBEDDING_BASE_URL", "https://api.openai.com/v1")
    assert not embeddings.available()  # OpenAI itself needs a key
    monkeypatch.setattr(config, "EMBEDDING_BASE_URL", "http://localhost:11434/v1")
    assert embeddings.available()  # a local server does not


def fake_post(calls, responder):
    """An httpx.post stand-in that records payloads and answers with `responder(payload)`."""
    def post(url, headers=None, json=None, timeout=None):
        """Record the request and return a response object whose raise_for_status raises on 4xx/5xx."""
        calls.append({"url": url, "json": dict(json), "auth": (headers or {}).get("Authorization")})
        status, body = responder(json)
        return SimpleNamespace(status_code=status, json=lambda: body, raise_for_status=lambda: None if status < 400
                               else (_ for _ in ()).throw(RuntimeError(f"HTTP {status}")))
    return post


def ok_body(payload):
    """A well-formed embeddings response for the request."""
    return 200, {"data": [{"index": i, "embedding": [float(i + 1), 0.0, 1.0, 0.0]} for i in range(len(payload["input"]))]}


def test_embed_texts_batches_and_keeps_order(monkeypatch):
    """Inputs larger than one batch are split into requests and return one vector per text."""
    calls = []
    monkeypatch.setattr(embeddings.httpx, "post", fake_post(calls, ok_body))
    vectors = embeddings.embed_texts([f"headline {i}" for i in range(embeddings.BATCH + 5)])
    assert len(vectors) == embeddings.BATCH + 5
    assert [len(c["json"]["input"]) for c in calls] == [embeddings.BATCH, 5]
    assert calls[0]["url"] == "https://embed.example/v1/embeddings" and calls[0]["auth"] == "Bearer key"
    assert calls[0]["json"]["dimensions"] == 4 and calls[0]["json"]["model"] == "test-embed"


def test_embed_texts_retries_without_dimensions_when_the_model_rejects_them(monkeypatch):
    """A 400 caused by the dimensions field triggers one retry without it."""
    calls = []
    monkeypatch.setattr(embeddings.httpx, "post", fake_post(calls, lambda p: (400, {}) if "dimensions" in p else ok_body(p)))
    assert embeddings.embed_texts(["a headline"]) is not None
    assert "dimensions" in calls[0]["json"] and "dimensions" not in calls[1]["json"]


def test_embed_texts_returns_none_on_failure_or_a_malformed_reply(monkeypatch):
    """Server errors and malformed or short replies yield None instead of raising."""
    monkeypatch.setattr(embeddings.httpx, "post", fake_post([], lambda p: (500, {})))
    assert embeddings.embed_texts(["x"]) is None
    monkeypatch.setattr(embeddings.httpx, "post", fake_post([], lambda p: (200, {"data": []})))
    assert embeddings.embed_texts(["x"]) is None  # wrong number of vectors
    monkeypatch.setattr(embeddings.httpx, "post", fake_post([], lambda p: (200, {"nope": 1})))
    assert embeddings.embed_texts(["x"]) is None


# --------------------------------------------------------------------------- #
# embed_pending
# --------------------------------------------------------------------------- #

@pytest.fixture()
def db():
    """In-memory database with a few articles."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as session:
        yield session


def add(db, i, **kw):
    """Add an article published an hour ago."""
    fields = dict(title=f"Story {i}", url=f"https://x.test/{i}", source="S", topic="World", sentiment=0.0,
                  published_at=NOW - timedelta(hours=1), is_seed=False)
    fields.update(kw)
    db.add(Article(**fields))


def test_embed_pending_stores_vectors_for_shared_articles_only(db, monkeypatch):
    """Only recent, shared, non-seed articles are sent for embedding and stored."""
    add(db, 1)
    add(db, 2, is_seed=True)                         # demo seed: never embedded
    add(db, 3, workspace_id="visitor")               # a visitor's article: never sent to a paid API
    add(db, 4, published_at=NOW - timedelta(days=30))  # too old for clustering to use
    db.commit()
    seen = []
    # Record which texts are sent and answer with one dummy vector each.
    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: (seen.extend(texts), [[1.0, 0.0, 0.0, 0.0]] * len(texts))[1])
    assert embeddings.embed_pending(db) == 1
    assert len(seen) == 1 and seen[0].startswith("Story 1")
    stored = {a.title: a for a in db.execute(select(Article)).scalars()}
    assert stored["Story 1"].embedding and stored["Story 1"].embedding_model == "test-embed"
    assert not stored["Story 2"].embedding and not stored["Story 4"].embedding
    db.info["workspace"] = "visitor"  # the visitor's article is only visible from their own session
    assert not db.execute(select(Article).where(Article.title == "Story 3")).scalar_one().embedding


def test_embed_pending_does_nothing_when_off_or_for_a_workspace_session(db, monkeypatch):
    """A visitor session or disabled embeddings never call the provider."""
    add(db, 1)
    db.commit()
    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: pytest.fail("must not call the provider"))
    db.info["workspace"] = "visitor"
    assert embeddings.embed_pending(db) == 0
    db.info["workspace"] = ""
    monkeypatch.setattr(config, "EMBEDDINGS_ENABLED", False)
    assert embeddings.embed_pending(db) == 0


def test_embed_pending_survives_a_provider_failure_and_reembeds_after_a_model_change(db, monkeypatch):
    """A failed provider call stores nothing, and switching models re-embeds stored articles."""
    add(db, 1)
    db.commit()
    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: None)
    assert embeddings.embed_pending(db) == 0 and db.execute(select(Article)).scalar_one().embedding is None
    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[1.0, 0.0, 0.0, 0.0]] * len(texts))
    assert embeddings.embed_pending(db) == 1
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "newer-model")
    assert embeddings.embed_pending(db) == 1  # vectors from another model are not comparable, so they are redone
    assert db.execute(select(Article)).scalar_one().embedding_model == "newer-model"


def test_vectors_from_another_model_are_ignored_by_clustering(monkeypatch):
    """Only decodable vectors from the current model are handed to clustering."""
    blob = embeddings.encode([1.0, 0.0, 0.0, 0.0])
    got = embeddings.vectors_for([(1, blob, "test-embed"), (2, blob, "older-model"), (3, None, None), (4, "!!bad!!", "test-embed")])
    assert set(got) == {1}


# --------------------------------------------------------------------------- #
# Clustering by meaning
# --------------------------------------------------------------------------- #

def test_paraphrases_with_no_shared_words_cluster_when_their_meaning_is_close():
    """Headlines sharing no words still cluster when their vectors are close."""
    titles = ["Regulators halt every domestic departure", "Air travel paralysed across the country"]
    assert cluster_rows(rows(titles)) == []  # words alone cannot tell
    close = {1: unit(1, 0.2, 0, 0), 2: unit(1, 0.3, 0.1, 0)}
    clusters = cluster_rows(rows(titles), close)
    assert len(clusters) == 1 and clusters[0].article_ids == (1, 2)


def test_distant_meaning_does_not_cluster():
    """Vectors below the similarity threshold keep headlines apart."""
    titles = ["Regulators halt every domestic departure", "Central bank holds interest rates steady"]
    far = {1: unit(1, 0, 0, 0), 2: unit(0.3, 1, 0, 0)}
    assert cluster_rows(rows(titles), far) == []


def test_meaning_cannot_link_stories_published_days_apart():
    """Identical vectors do not merge articles published five days apart."""
    titles = ["Regulators halt every domestic departure", "Air travel paralysed across the country"]
    same = {1: unit(1, 0, 0, 0), 2: unit(1, 0, 0, 0)}
    assert cluster_rows(rows(titles, hours=24 * 5), same) == []


def test_articles_without_vectors_still_cluster_by_words_alongside_embedded_ones():
    """Word-based and vector-based matching both work in the same clustering run."""
    clusters = cluster_rows(rows([
        "FAA issues nationwide ground stop due to extraordinary circumstances",
        "FAA ground stop shuts down flights nationwide",
        "Regulators halt every domestic departure",
        "Air travel paralysed across the country",
    ]), {3: unit(1, 0.2, 0, 0), 4: unit(1, 0.3, 0.1, 0)})
    assert sorted(c.article_ids for c in clusters) == [(1, 2), (3, 4)]


def test_a_chain_bridged_by_one_headline_is_split_into_its_two_stories():
    """An oversized cluster chained through one bridging headline splits back into its two real stories."""
    a, b = unit(1, 0), unit(0.3, math.sqrt(1 - 0.09))   # about 72 degrees apart: not the same story
    bridge = unit(*(a + b))                             # close enough to both (cosine about 0.81) to chain them
    # Two groups of n together exceed MAX_CLUSTER, forcing the split.
    n = MAX_CLUSTER // 2 + 2
    titles = [f"alpha{i}word{i} beta{i}word{i}" for i in range(2 * n + 1)]  # no shared words: only meaning links
    vectors = {i + 1: a for i in range(n)} | {n + i + 1: b for i in range(n)} | {2 * n + 1: bridge}
    assert max(len(c.article_ids) for c in cluster_rows(rows(titles), vectors) or [SimpleNamespace(article_ids=())]) <= MAX_CLUSTER
    clusters = cluster_rows(rows(titles), vectors)
    assert sorted(len(c.article_ids) for c in clusters) == [n, n]
    assert {c.article_ids for c in clusters} == {tuple(range(1, n + 1)), tuple(range(n + 1, 2 * n + 1))}


def test_story_index_uses_stored_embeddings(db, monkeypatch):
    """The story index clusters by stored vectors and ignores those from another model."""
    # Two wordless paraphrases with nearly identical stored vectors.
    for i, title in enumerate(["Regulators halt every domestic departure", "Air travel paralysed across the country"]):
        add(db, i + 1, title=title, source=f"Src{i}", embedding=embeddings.encode([1.0, 0.2 + i / 10, 0, 0]),
            embedding_model="test-embed")
    db.commit()
    story_index.reset_cache()
    by_article, by_id = story_index.get_clusters(db)
    assert len(by_id) == 1 and set(by_article) == {1, 2}
    # without usable vectors (another model) the same headlines stay apart
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "other")
    story_index.reset_cache()
    assert story_index.get_clusters(db)[1] == {}
    story_index.reset_cache()
