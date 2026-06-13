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

from app.domain.reservation import (
    Reservation,
    ReservationValidationCode,
    ReservationValidationError,
    SeatingPreference,
)
from app.repositories import reservation_repo
from app.services import reservation_draft_service

_TERRACE_MAX_PARTY = 5
_CALL_CENTER_MAX_PARTY = 14

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


async def get_by_id(session: AsyncSession, reservation_id: UUID) -> Reservation | None:
    """Return the Reservation with this ID, or None. FR-013."""
    return await reservation_repo.get_by_id(session, reservation_id)


async def find_active_by_customer(
    session: AsyncSession, customer_id: UUID
) -> list[Reservation]:
    """Return all ACTIVE reservations for this customer. FR-013, R9."""
    return await reservation_repo.find_active_by_customer(session, customer_id)


async def modify(
    session: AsyncSession,
    customer_id: UUID,
    reservation_id: UUID,
    fields: dict[str, object],
) -> Reservation:
    """Update allowed fields on an existing reservation; reference is never touched.

    Raises ReservationValidationError(PARTY_TOO_LARGE) when party_size > 14.
    Raises ReservationValidationError(TERRACE_TOO_LARGE) when the resulting
    (party_size, seating_preference) pair would exceed the terrace maximum. T033, FR-015.
    """
    current = await reservation_repo.get_by_id(session, reservation_id)
    if current is None:
        raise ValueError(f"Reservation {reservation_id} not found")

    # Party-too-large guard — mirrors collect_field guard (FR-007)
    if "party_size" in fields:
        ps = int(fields["party_size"])  # type: ignore[call-overload]
        if ps > _CALL_CENTER_MAX_PARTY:
            raise ReservationValidationError(
                ReservationValidationCode.PARTY_TOO_LARGE, str(ps)
            )

    # Terrace conflict guard — effective state after the update (T033, FR-015)
    effective_party_size = int(fields.get("party_size", current.party_size))  # type: ignore[call-overload]
    effective_seating = fields.get("seating_preference", current.seating_preference)
    if (
        effective_seating == SeatingPreference.OUTDOOR_TERRACE
        and effective_party_size > _TERRACE_MAX_PARTY
    ):
        raise ReservationValidationError(
            ReservationValidationCode.TERRACE_TOO_LARGE, str(effective_party_size)
        )

    updated = await reservation_repo.update_fields(session, reservation_id, **fields)
    if updated is None:
        raise ValueError(f"Reservation {reservation_id} disappeared after update")

    logger.info(
        "reservation_modified",
        extra={
            "reservation_id": str(reservation_id),
            "customer_id": str(customer_id),
            "fields": list(fields.keys()),
        },
    )
    return updated
