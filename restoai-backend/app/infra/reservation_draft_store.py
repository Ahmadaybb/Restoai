"""Redis-only ReservationDraft store — 002-reservations.

Key: res_draft:{customer_id}  TTL: DRAFT_TTL (2h)

Separate key prefix from order drafts (draft:{customer_id}) to avoid
collision. See research.md R10, ADR-012.
"""
import json
from typing import Any
from uuid import UUID

from app.infra.redis_client import DRAFT_TTL, get_redis


def _key(customer_id: UUID | str) -> str:
    return f"res_draft:{customer_id}"


async def get_res_draft(customer_id: UUID | str) -> dict[str, Any] | None:
    raw = await get_redis().get(_key(customer_id))
    if raw is None:
        return None
    return json.loads(raw)  # type: ignore[no-any-return]


async def put_res_draft(customer_id: UUID | str, draft: dict[str, Any]) -> None:
    await get_redis().setex(
        _key(customer_id), DRAFT_TTL, json.dumps(draft, default=str)
    )


async def delete_res_draft(customer_id: UUID | str) -> None:
    await get_redis().delete(_key(customer_id))
