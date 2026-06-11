"""Per-call cost logging for every LLM and embedding call.

Schema (constitution Principle IV):
  {ts, request_id, provider, model, tier, input_tokens, output_tokens,
   est_cost_usd, latency_ms}

Call log_cost() inside every GroqClient and EmbedderClient method, after the
call completes.
"""
import logging
from dataclasses import asdict, dataclass
from typing import Literal

from app.infra.logging import request_id_var

logger = logging.getLogger("restoai.cost")


@dataclass
class CostRecord:
    provider: str
    model: str
    tier: Literal["mechanical", "synthesis", "embedding"]
    input_tokens: int
    output_tokens: int
    est_cost_usd: float
    latency_ms: float
    request_id: str = ""

    def __post_init__(self) -> None:
        if not self.request_id:
            self.request_id = request_id_var.get()


def log_cost(
    *,
    provider: str,
    model: str,
    tier: Literal["mechanical", "synthesis", "embedding"],
    input_tokens: int,
    output_tokens: int,
    est_cost_usd: float,
    latency_ms: float,
) -> None:
    record = CostRecord(
        provider=provider,
        model=model,
        tier=tier,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        est_cost_usd=est_cost_usd,
        latency_ms=latency_ms,
    )
    logger.info("cost_record", extra=asdict(record))
