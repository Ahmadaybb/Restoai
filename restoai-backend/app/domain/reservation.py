"""Reservation domain models — 002-reservations.

Covers ReservationDraft (Redis-only, 2h TTL), Reservation (Postgres),
SeatingPreference enum, ReservationState, ReservationValidationCode/Error.
FR-003–FR-012, FR-015, FR-016b; data-model.md.
"""
from __future__ import annotations

import datetime as _dt
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from app.domain.language import Language

_TERRACE_MAX_PARTY = 5
_CALL_CENTER_MAX_PARTY = 14


class SeatingPreference(StrEnum):
    INDOOR_SMOKING = "indoor_smoking"
    INDOOR_NON_SMOKING = "indoor_non_smoking"
    OUTDOOR_TERRACE = "outdoor_terrace"
    OUTDOOR_NON_TERRACE = "outdoor_non_terrace"


class ReservationState(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


class ReservationValidationCode(StrEnum):
    MISSING_DATE = "missing_date"
    PAST_DATE = "past_date"
    MISSING_TIME = "missing_time"
    MISSING_PARTY_SIZE = "missing_party_size"
    PARTY_TOO_LARGE = "party_too_large"
    MISSING_NAME = "missing_name"
    MISSING_PHONE = "missing_phone"
    MISSING_SEATING = "missing_seating"
    TERRACE_TOO_LARGE = "terrace_too_large"


class ReservationValidationError(Exception):
    """Raised when a ReservationDraft fails pre-confirmation validation."""

    def __init__(self, code: ReservationValidationCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}" if detail else code.value)


class ReservationDraft(BaseModel):
    """In-progress reservation during field collection. Redis-only, 2h TTL."""

    id: UUID = Field(default_factory=uuid4)
    customer_id: UUID
    date: _dt.date | None = None
    time: _dt.time | None = None
    party_size: int | None = None
    name: str | None = None
    phone: str | None = None
    seating_preference: SeatingPreference | None = None
    language: Language = Language.EN
    created_at: _dt.datetime = Field(default_factory=_dt.datetime.utcnow)
    updated_at: _dt.datetime = Field(default_factory=_dt.datetime.utcnow)

    @field_validator("party_size")
    @classmethod
    def _party_size_positive(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("party_size must be >= 1")
        return v

    def validate_ready_to_confirm(self) -> None:
        """Raise ReservationValidationError for the first failing rule. FR-006–FR-009."""
        today = _dt.datetime.utcnow().date()

        if self.date is None:
            raise ReservationValidationError(ReservationValidationCode.MISSING_DATE)
        if self.date < today:
            raise ReservationValidationError(ReservationValidationCode.PAST_DATE, str(self.date))
        if self.time is None:
            raise ReservationValidationError(ReservationValidationCode.MISSING_TIME)
        if self.party_size is None:
            raise ReservationValidationError(ReservationValidationCode.MISSING_PARTY_SIZE)
        if self.party_size > _CALL_CENTER_MAX_PARTY:
            raise ReservationValidationError(
                ReservationValidationCode.PARTY_TOO_LARGE, str(self.party_size)
            )
        if not self.name or not self.name.strip():
            raise ReservationValidationError(ReservationValidationCode.MISSING_NAME)
        if not self.phone or not self.phone.strip():
            raise ReservationValidationError(ReservationValidationCode.MISSING_PHONE)
        if self.seating_preference is None:
            raise ReservationValidationError(ReservationValidationCode.MISSING_SEATING)
        if (
            self.seating_preference == SeatingPreference.OUTDOOR_TERRACE
            and self.party_size > _TERRACE_MAX_PARTY
        ):
            raise ReservationValidationError(
                ReservationValidationCode.TERRACE_TOO_LARGE, str(self.party_size)
            )


class Reservation(BaseModel):
    """Confirmed table reservation persisted to Postgres."""

    id: UUID = Field(default_factory=uuid4)
    reference: str = Field(min_length=7, max_length=12)
    customer_id: UUID
    date: _dt.date
    time: _dt.time
    party_size: int = Field(ge=1, le=_CALL_CENTER_MAX_PARTY)
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=20)
    seating_preference: SeatingPreference
    state: ReservationState = ReservationState.ACTIVE
    language: Language
    created_at: _dt.datetime = Field(default_factory=_dt.datetime.utcnow)
    updated_at: _dt.datetime = Field(default_factory=_dt.datetime.utcnow)
    cancelled_at: _dt.datetime | None = None
