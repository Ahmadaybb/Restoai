"""ReservationRepository — Postgres-backed reservation access.

SQL only — never raises HTTP errors. Imported only by app/services/.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Reservation as ReservationORM
from app.domain.reservation import Reservation, ReservationState, SeatingPreference


def _orm_to_domain(row: ReservationORM) -> Reservation:
    return Reservation(
        id=row.id,
        reference=row.reference,
        customer_id=row.customer_id,
        date=row.date,
        time=row.time,
        party_size=row.party_size,
        name=row.name,
        phone=row.phone,
        seating_preference=SeatingPreference(row.seating_preference),
        state=ReservationState(row.state),
        language=row.language,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        cancelled_at=row.cancelled_at,
    )


async def create(session: AsyncSession, reservation: Reservation) -> Reservation:
    row = ReservationORM(
        id=reservation.id,
        reference=reservation.reference,
        customer_id=reservation.customer_id,
        date=reservation.date,
        time=reservation.time,
        party_size=reservation.party_size,
        name=reservation.name,
        phone=reservation.phone,
        seating_preference=reservation.seating_preference.value,
        state=reservation.state.value,
        language=reservation.language,
    )
    session.add(row)
    await session.flush()
    return reservation


async def get_by_id(
    session: AsyncSession, reservation_id: uuid.UUID
) -> Reservation | None:
    result = await session.execute(
        select(ReservationORM).where(ReservationORM.id == reservation_id)
    )
    row = result.scalar_one_or_none()
    return _orm_to_domain(row) if row else None


async def find_active_by_customer(
    session: AsyncSession, customer_id: uuid.UUID
) -> list[Reservation]:
    result = await session.execute(
        select(ReservationORM).where(
            ReservationORM.customer_id == customer_id,
            ReservationORM.state == ReservationState.ACTIVE.value,
        )
    )
    return [_orm_to_domain(row) for row in result.scalars().all()]


async def update_fields(
    session: AsyncSession,
    reservation_id: uuid.UUID,
    **kwargs: object,
) -> Reservation | None:
    kwargs["updated_at"] = datetime.now(tz=UTC)
    await session.execute(
        update(ReservationORM)
        .where(ReservationORM.id == reservation_id)
        .values(**kwargs)
    )
    await session.flush()
    return await get_by_id(session, reservation_id)


async def cancel(
    session: AsyncSession, reservation_id: uuid.UUID
) -> Reservation | None:
    return await update_fields(
        session,
        reservation_id,
        state=ReservationState.CANCELLED.value,
        cancelled_at=datetime.now(tz=UTC),
    )
