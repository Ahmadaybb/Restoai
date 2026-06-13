"""Voyage AI cloud embedder — voyage-multilingual-2.

Implements app.domain.clients.EmbeddingClient protocol.
Cost: ~$0.06 per 1M tokens.
"""
import logging
import time

import voyageai

from app.infra.cost_log import log_cost
from app.infra.settings import get_settings

logger = logging.getLogger(__name__)

_MODEL = "voyage-multilingual-2"
_COST_PER_TOKEN = 6e-8  # $0.06 per 1M tokens


def is_loaded() -> bool:
    """Returns True once settings are validated — Voyage AI needs no local model load."""
    return bool(get_settings().VOYAGE_API_KEY)


class EmbedderClient:
    """Async wrapper around the Voyage AI embedding API."""

    def __init__(self) -> None:
        self._client = voyageai.AsyncClient(api_key=get_settings().VOYAGE_API_KEY)  # type: ignore[attr-defined]

    async def embed_query(self, text: str) -> list[float]:
        t0 = time.monotonic()
        result = await self._client.embed([text], model=_MODEL, input_type="query")
        latency_ms = (time.monotonic() - t0) * 1000
        log_cost(
            provider="voyage",
            model=_MODEL,
            tier="embedding",
            input_tokens=result.total_tokens,
            output_tokens=0,
            est_cost_usd=result.total_tokens * _COST_PER_TOKEN,
            latency_ms=latency_ms,
        )
        return [float(v) for v in result.embeddings[0]]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        t0 = time.monotonic()
        result = await self._client.embed(texts, model=_MODEL, input_type="document")
        latency_ms = (time.monotonic() - t0) * 1000
        log_cost(
            provider="voyage",
            model=_MODEL,
            tier="embedding",
            input_tokens=result.total_tokens,
            output_tokens=0,
            est_cost_usd=result.total_tokens * _COST_PER_TOKEN,
            latency_ms=latency_ms,
        )
        return [[float(v) for v in vec] for vec in result.embeddings]
