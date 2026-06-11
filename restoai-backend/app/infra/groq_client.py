"""Groq LLM client — two async tiers: mechanical and synthesis.

Every call emits a structured cost-log record correlated by request_id
(constitution Principle IV; research.md R3).

Implements app.domain.clients.LLMClient protocol.
"""
import logging
import time
from typing import Any

from groq import AsyncGroq

from app.infra.cost_log import log_cost

logger = logging.getLogger(__name__)

# Model ids — update here when Groq rotates aliases
_MECHANICAL_MODEL = "llama-3.1-8b-instant"
_SYNTHESIS_MODEL = "llama-3.1-70b-versatile"

# Approximate cost per 1M tokens (USD) — update quarterly per cost log review
_COST_PER_1M: dict[str, dict[str, float]] = {
    _MECHANICAL_MODEL: {"input": 0.05, "output": 0.08},
    _SYNTHESIS_MODEL: {"input": 0.59, "output": 0.79},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = _COST_PER_1M.get(model, {"input": 0.0, "output": 0.0})
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


class GroqClient:
    """Async Groq client implementing the LLMClient protocol."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncGroq(api_key=api_key)

    async def _complete(
        self,
        *,
        model: str,
        tier: str,
        system: str,
        user: str,
        response_format: type[Any] | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if response_format is not None:
            kwargs["response_format"] = {"type": "json_object"}

        t0 = time.monotonic()
        response = await self._client.chat.completions.create(**kwargs)
        latency_ms = (time.monotonic() - t0) * 1000

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        log_cost(
            provider="groq",
            model=model,
            tier=tier,  # type: ignore[arg-type]
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            est_cost_usd=_estimate_cost(model, input_tokens, output_tokens),
            latency_ms=latency_ms,
        )

        content = response.choices[0].message.content or ""
        return content

    async def complete_mechanical(
        self,
        *,
        system: str,
        user: str,
        response_format: type[Any] | None = None,
    ) -> str:
        return await self._complete(
            model=_MECHANICAL_MODEL,
            tier="mechanical",
            system=system,
            user=user,
            response_format=response_format,
        )

    async def complete_synthesis(
        self,
        *,
        system: str,
        user: str,
        response_format: type[Any] | None = None,
    ) -> str:
        return await self._complete(
            model=_SYNTHESIS_MODEL,
            tier="synthesis",
            system=system,
            user=user,
            response_format=response_format,
        )
