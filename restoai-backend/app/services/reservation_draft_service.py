"""ReservationDraftService — all ReservationDraft mutations against Redis.

FR-002, FR-004, FR-009, FR-015; data-model.md §ReservationDraft, research.md R13.
Drafts are Redis-only (same rationale as OrderDraft — ADR-007/ADR-012).
"""
from __future__ import annotations

import logging
from uuid import UUID

from app.domain.customer import Customer
from app.domain.language import Language
from app.domain.reservation import (
    ReservationDraft,
    ReservationValidationCode,
    ReservationValidationError,
)
from app.infra import reservation_draft_store

_CALL_CENTER_MAX_PARTY = 14

logger = logging.getLogger(__name__)


def _serialize(draft: ReservationDraft) -> dict[str, object]:
    return draft.model_dump(mode="json")


def _deserialize(raw: dict[str, object]) -> ReservationDraft:
    return ReservationDraft.model_validate(raw)


async def start_draft(customer_id: UUID, language: Language) -> ReservationDraft:
    """Create a fresh draft and persist it. Overwrites any existing draft."""
    draft = ReservationDraft(customer_id=customer_id, language=language)
    await reservation_draft_store.put_res_draft(customer_id, _serialize(draft))
    return draft


async def get_draft(customer_id: UUID) -> ReservationDraft | None:
    """Return the active draft for this customer, or None."""
    raw = await reservation_draft_store.get_res_draft(customer_id)
    if raw is None:
        return None
    return _deserialize(raw)


async def delete_draft(customer_id: UUID) -> None:
    """Remove the draft (e.g. after confirmation or cancellation)."""
    await reservation_draft_store.delete_res_draft(customer_id)


async def collect_field(
    customer_id: UUID,
    field_name: str,
    value: object,
) -> ReservationDraft:
    """Set one field on the active draft and refresh its TTL.

    Raises ValueError if no draft is active — callers must call start_draft first.
    Raises ReservationValidationError(PARTY_TOO_LARGE) immediately when party_size > 14
    so the caller can redirect to the call center before writing anything. FR-007.
    """
    if field_name == "party_size" and isinstance(value, int) and value > _CALL_CENTER_MAX_PARTY:
        raise ReservationValidationError(
            ReservationValidationCode.PARTY_TOO_LARGE, str(value)
        )
    draft = await get_draft(customer_id)
    if draft is None:
        raise ValueError(f"No active reservation draft for customer {customer_id}")
    updated = draft.model_copy(update={field_name: value})
    await reservation_draft_store.put_res_draft(customer_id, _serialize(updated))
    return updated


async def prefill_from_customer(
    customer_id: UUID,
    customer: Customer,
) -> ReservationDraft:
    """Pre-populate name and phone from the Customer record if not already set.

    No-ops if no draft is active. FR-004, research.md R13.
    """
    draft = await get_draft(customer_id)
    if draft is None:
        raise ValueError(f"No active reservation draft for customer {customer_id}")
    updates: dict[str, object] = {}
    if not draft.name and customer.display_name:
        updates["name"] = customer.display_name
    if not draft.phone and customer.phone_e164:
        updates["phone"] = customer.phone_e164
    if not updates:
        return draft
    updated = draft.model_copy(update=updates)
    await reservation_draft_store.put_res_draft(customer_id, _serialize(updated))
    return updated


async def validate_ready_to_confirm(customer_id: UUID) -> ReservationDraft:
    """Return the draft if all 9 validation rules pass; raise ReservationValidationError otherwise.

    Raises ValueError if no draft is active.
    """
    draft = await get_draft(customer_id)
    if draft is None:
        raise ValueError(f"No active reservation draft for customer {customer_id}")
    draft.validate_ready_to_confirm()  # propagates ReservationValidationError
    return draft
