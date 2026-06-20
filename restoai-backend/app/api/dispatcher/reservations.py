"""Dispatcher REST surface for reservations.

GET  /api/dispatcher/reservations — list all reservations
POST /api/dispatcher/reservations — create a reservation (dispatcher-initiated)
"""
import datetime
import logging
import random
import string
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.dispatcher.auth import require_auth
from app.domain.reservation import Reservation, ReservationState, ReservationValidationCode, ReservationValidationError, SeatingPreference
from app.domain.language import Language
from app.repositories import reservation_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dispatcher", tags=["dispatcher"])


class ReservationOut(BaseModel):
    id: UUID
    reference: str
    date: datetime.date
    time: datetime.time
    party_size: int
    name: str
    phone: str
    seating_preference: str
    state: str
    language: str
    created_at: datetime.datetime
    cancelled_at: datetime.datetime | None = None


class ReservationCreateIn(BaseModel):
    name: str
    phone: str
    date: datetime.date
    time: str  # HH:MM in 24h
    party_size: int
    seating_preference: str  # SeatingPreference value
    notes: str = ""


def _gen_reference() -> str:
    return "LF-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=5))


def _to_out(r: Reservation) -> ReservationOut:
    return ReservationOut(
        id=r.id,
        reference=r.reference,
        date=r.date,
        time=r.time,
        party_size=r.party_size,
        name=r.name,
        phone=r.phone,
        seating_preference=r.seating_preference.value,
        state=r.state.value,
        language=r.language.value if hasattr(r.language, "value") else str(r.language),
        created_at=r.created_at,
        cancelled_at=r.cancelled_at,
    )


@router.get("/reservations", response_model=list[ReservationOut])
async def list_reservations(
    _token: Annotated[str, Depends(require_auth)],
    session: Annotated[AsyncSession, Depends(get_session)],
    date: datetime.date | None = Query(default=None, description="Filter by date (YYYY-MM-DD)"),
    state: str | None = Query(default=None, description="Filter by state: active | cancelled"),
) -> list[ReservationOut]:
    state_enum: ReservationState | None = None
    if state is not None:
        try:
            state_enum = ReservationState(state)
        except ValueError:
            state_enum = None

    reservations = await reservation_repo.list_all(session, date=date, state=state_enum)
    logger.info("dispatcher_list_reservations", extra={"count": len(reservations)})
    return [_to_out(r) for r in reservations]


@router.post("/reservations", response_model=ReservationOut, status_code=201)
async def create_reservation(
    body: ReservationCreateIn,
    _token: Annotated[str, Depends(require_auth)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReservationOut:
    """Create a reservation from the dispatcher portal (no associated customer)."""
    try:
        seating = SeatingPreference(body.seating_preference)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid seating_preference: {body.seating_preference}")

    try:
        hour, minute = (int(x) for x in body.time.split(":"))
        res_time = datetime.time(hour, minute)
    except Exception:
        raise HTTPException(status_code=422, detail="time must be HH:MM in 24-hour format")

    reservation = Reservation(
        reference=_gen_reference(),
        customer_id=None,
        date=body.date,
        time=res_time,
        party_size=body.party_size,
        name=body.name.strip(),
        phone=body.phone.strip(),
        seating_preference=seating,
        language=Language.EN,
    )

    saved = await reservation_repo.create(session, reservation)
    await session.commit()
    logger.info("dispatcher_created_reservation", extra={"id": str(saved.id), "reference": saved.reference})
    return _to_out(saved)
