"""Dispatcher REST surface for reservations.

GET /api/dispatcher/reservations — list all reservations, optionally
filtered by date (YYYY-MM-DD) and/or state (active | cancelled).
"""
import datetime
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.dispatcher.auth import require_auth
from app.domain.reservation import ReservationState
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
    return [
        ReservationOut(
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
        for r in reservations
    ]
