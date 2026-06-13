"""ReservationService — the only path that creates a confirmed Reservation.

FR-010, FR-011, FR-012; research.md R3, R6.
confirm() validates the draft, generates the reference, persists to Postgres,
and deletes the Redis draft.
"""
from __future__ import annotations

import logging
import secrets
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.reservation import Reservation
from app.repositories import reservation_repo
from app.services import reservation_draft_service

logger = logging.getLogger(__name__)


def _generate_reference() -> str:
    """RES- + 7 uppercase hex chars (token_hex(4) → 8 hex chars, [:7] takes first 7)."""
    return "RES-" + secrets.token_hex(4).upper()[:7]


async def confirm(session: AsyncSession, customer_id: UUID) -> Reservation:
    """FR-010, FR-011, FR-012: Validate draft, create Reservation row, delete draft."""
    draft = await reservation_draft_service.validate_ready_to_confirm(customer_id)

    reference = _generate_reference()
    reservation = Reservation(
        customer_id=draft.customer_id,
        reference=reference,
        date=draft.date,  # type: ignore[arg-type]
        time=draft.time,  # type: ignore[arg-type]
        party_size=draft.party_size,  # type: ignore[arg-type]
        name=draft.name,  # type: ignore[arg-type]
        phone=draft.phone,  # type: ignore[arg-type]
        seating_preference=draft.seating_preference,  # type: ignore[arg-type]
        language=draft.language,
    )

    await reservation_repo.create(session, reservation)
    await reservation_draft_service.delete_draft(customer_id)

    logger.info(
        "reservation_confirmed",
        extra={
            "reservation_id": str(reservation.id),
            "customer_id": str(customer_id),
            "reference": reference,
        },
    )
    return reservation
