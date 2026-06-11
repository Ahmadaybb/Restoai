"""Redis-only OrderDraft + failure-counter store.

Keys (all with DRAFT_TTL = 7200 s):
  draft:{customer_id}          — JSON blob of the active OrderDraft
  failcount:{customer_id}:{field} — int failure counter
  chat_state:{customer_id}     — JSON blob of current conversation expectation

There is no Postgres mirror of in-flight drafts (research.md R6 / ADR-007).
"""
import json
from typing import Any
from uuid import UUID

from app.infra.redis_client import DRAFT_TTL, get_redis


def _draft_key(customer_id: UUID | str) -> str:
    return f"draft:{customer_id}"


def _failcount_key(customer_id: UUID | str, field: str) -> str:
    return f"failcount:{customer_id}:{field}"


def _chat_state_key(customer_id: UUID | str) -> str:
    return f"chat_state:{customer_id}"


# ── Draft operations ──────────────────────────────────────────────────────────

async def get_draft(customer_id: UUID | str) -> dict[str, Any] | None:
    raw = await get_redis().get(_draft_key(customer_id))
    if raw is None:
        return None
    return json.loads(raw)  # type: ignore[no-any-return]


async def put_draft(customer_id: UUID | str, draft: dict[str, Any]) -> None:
    await get_redis().setex(
        _draft_key(customer_id), DRAFT_TTL, json.dumps(draft, default=str)
    )


async def delete_draft(customer_id: UUID | str) -> None:
    await get_redis().delete(_draft_key(customer_id))


# ── Failure-counter operations ────────────────────────────────────────────────

async def incr_failcount(customer_id: UUID | str, field: str) -> int:
    """Increment failure counter and refresh TTL. Returns new count."""
    key = _failcount_key(customer_id, field)
    pipe = get_redis().pipeline()
    pipe.incr(key)
    pipe.expire(key, DRAFT_TTL)
    results = await pipe.execute()
    return int(results[0])


async def reset_failcount(customer_id: UUID | str, field: str) -> None:
    await get_redis().delete(_failcount_key(customer_id, field))


async def get_failcount(customer_id: UUID | str, field: str) -> int:
    val = await get_redis().get(_failcount_key(customer_id, field))
    return int(val) if val is not None else 0


# ── Chat-state operations ─────────────────────────────────────────────────────

async def get_chat_state(customer_id: UUID | str) -> dict[str, Any] | None:
    raw = await get_redis().get(_chat_state_key(customer_id))
    if raw is None:
        return None
    return json.loads(raw)  # type: ignore[no-any-return]


async def put_chat_state(customer_id: UUID | str, state: dict[str, Any]) -> None:
    await get_redis().setex(
        _chat_state_key(customer_id), DRAFT_TTL, json.dumps(state, default=str)
    )
