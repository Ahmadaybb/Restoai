"""Local sentence-transformers embedder — intfloat/multilingual-e5-large.

The model (1.3 GB) is loaded once at app lifespan startup and cached.
All inference is offloaded to a thread pool via asyncio.to_thread so the
async request path stays non-blocking (constitution Principle IV; research.md R2).

Implements app.domain.clients.EmbeddingClient protocol.

Cost logging: latency is recorded per call; est_cost_usd is 0.0 (local model)
for uniform accounting with the Groq path (constitution Principle IV).
"""
import asyncio
import logging
import time

from app.infra.cost_log import log_cost

logger = logging.getLogger(__name__)

_MODEL_NAME = "intfloat/multilingual-e5-large"

_embedder: object = None  # sentence_transformers.SentenceTransformer


def load_embedder(model_name: str = _MODEL_NAME) -> None:
    global _embedder
    from sentence_transformers import SentenceTransformer

    logger.info("loading_embedder", extra={"model": model_name})
    _embedder = SentenceTransformer(model_name)
    logger.info("embedder_loaded", extra={"model": model_name})


def is_loaded() -> bool:
    return _embedder is not None


def _sync_embed(texts: list[str]) -> list[list[float]]:
    if _embedder is None:
        raise RuntimeError("Embedder not loaded; call load_embedder() first.")
    vecs = _embedder.encode(texts, normalize_embeddings=True)  # type: ignore[attr-defined]
    return [v.tolist() for v in vecs]


class EmbedderClient:
    """Async wrapper around the local sentence-transformers model."""

    async def embed_query(self, text: str) -> list[float]:
        prefixed = f"query: {text}"
        t0 = time.monotonic()
        vectors = await asyncio.to_thread(_sync_embed, [prefixed])
        latency_ms = (time.monotonic() - t0) * 1000
        log_cost(
            provider="local",
            model=_MODEL_NAME,
            tier="embedding",
            input_tokens=len(text.split()),
            output_tokens=0,
            est_cost_usd=0.0,
            latency_ms=latency_ms,
        )
        return vectors[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefixed = [f"passage: {t}" for t in texts]
        t0 = time.monotonic()
        vectors = await asyncio.to_thread(_sync_embed, prefixed)
        latency_ms = (time.monotonic() - t0) * 1000
        total_tokens = sum(len(t.split()) for t in texts)
        log_cost(
            provider="local",
            model=_MODEL_NAME,
            tier="embedding",
            input_tokens=total_tokens,
            output_tokens=0,
            est_cost_usd=0.0,
            latency_ms=latency_ms,
        )
        return vectors
