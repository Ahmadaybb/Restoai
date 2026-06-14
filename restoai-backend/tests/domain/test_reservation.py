"""Unit tests for ReservationDraft validation — all 9 ReservationValidationCode paths.

Constitution Principle II: tests defined before implementation is wired.
"""
import json
from datetime import date, datetime, time, timedelta
from uuid import uuid4

import pytest

from app.domain.language import Language
from app.domain.reservation import (
    _CALL_CENTER_MAX_PARTY,
    _TERRACE_MAX_PARTY,
    Reservation,
    ReservationDraft,
    ReservationState,
    ReservationValidationCode,
    ReservationValidationError,
    SeatingPreference,
)

# ── helpers ───────────────────────────────────────────────────────────────────

def _tomorrow() -> date:
    return datetime.utcnow().date() + timedelta(days=1)


def _valid_draft(**overrides: object) -> ReservationDraft:
    defaults = dict(
        customer_id=uuid4(),
        date=_tomorrow(),
        time=time(19, 0),
        party_size=4,
        name="Alice",
        phone="+96171234567",
        seating_preference=SeatingPreference.INDOOR_NON_SMOKING,
        language=Language.EN,
    )
    defaults.update(overrides)
    return ReservationDraft(**defaults)


# ── SeatingPreference enum exhaustiveness ─────────────────────────────────────

def test_seating_preference_all_values() -> None:
    expected = {
        "indoor_smoking",
        "indoor_non_smoking",
        "outdoor_terrace",
        "outdoor_non_terrace",
    }
    actual = {v.value for v in SeatingPreference}
    assert actual == expected


# ── validate_ready_to_confirm — each of 9 error codes ────────────────────────

@pytest.mark.parametrize(
    "field,value,expected_code",
    [
        # missing_date
        ("date", None, ReservationValidationCode.MISSING_DATE),
        # missing_time
        ("time", None, ReservationValidationCode.MISSING_TIME),
        # missing_party_size
        ("party_size", None, ReservationValidationCode.MISSING_PARTY_SIZE),
        # missing_name — empty string
        ("name", "", ReservationValidationCode.MISSING_NAME),
        # missing_name — whitespace-only
        ("name", "   ", ReservationValidationCode.MISSING_NAME),
        # missing_phone — empty string
        ("phone", "", ReservationValidationCode.MISSING_PHONE),
        # missing_phone — whitespace-only
        ("phone", "  ", ReservationValidationCode.MISSING_PHONE),
        # missing_seating
        ("seating_preference", None, ReservationValidationCode.MISSING_SEATING),
    ],
)
def test_validation_missing_fields(
    field: str, value: object, expected_code: ReservationValidationCode
) -> None:
    draft = _valid_draft(**{field: value})
    with pytest.raises(ReservationValidationError) as exc_info:
        draft.validate_ready_to_confirm()
    assert exc_info.value.code == expected_code


def test_validation_past_date() -> None:
    yesterday = datetime.utcnow().date() - timedelta(days=1)
    draft = _valid_draft(date=yesterday)
    with pytest.raises(ReservationValidationError) as exc_info:
        draft.validate_ready_to_confirm()
    assert exc_info.value.code == ReservationValidationCode.PAST_DATE


def test_validation_party_too_large() -> None:
    draft = _valid_draft(
        party_size=_CALL_CENTER_MAX_PARTY + 1,
        seating_preference=SeatingPreference.INDOOR_NON_SMOKING,
    )
    with pytest.raises(ReservationValidationError) as exc_info:
        draft.validate_ready_to_confirm()
    assert exc_info.value.code == ReservationValidationCode.PARTY_TOO_LARGE


def test_validation_terrace_too_large() -> None:
    draft = _valid_draft(
        party_size=_TERRACE_MAX_PARTY + 1,
        seating_preference=SeatingPreference.OUTDOOR_TERRACE,
    )
    with pytest.raises(ReservationValidationError) as exc_info:
        draft.validate_ready_to_confirm()
    assert exc_info.value.code == ReservationValidationCode.TERRACE_TOO_LARGE


def test_validation_terrace_at_max_party_size_passes() -> None:
    """Exactly at terrace limit must not raise terrace_too_large."""
    draft = _valid_draft(
        party_size=_TERRACE_MAX_PARTY,
        seating_preference=SeatingPreference.OUTDOOR_TERRACE,
    )
    draft.validate_ready_to_confirm()  # must not raise


def test_validation_valid_draft_passes() -> None:
    _valid_draft().validate_ready_to_confirm()  # must not raise


# ── Validation error ordering: party_too_large checked before terrace ─────────

def test_party_too_large_checked_before_terrace_too_large() -> None:
    """A party > 14 asking for terrace triggers party_too_large, not terrace_too_large."""
    draft = _valid_draft(
        party_size=_CALL_CENTER_MAX_PARTY + 1,
        seating_preference=SeatingPreference.OUTDOOR_TERRACE,
    )
    with pytest.raises(ReservationValidationError) as exc_info:
        draft.validate_ready_to_confirm()
    assert exc_info.value.code == ReservationValidationCode.PARTY_TOO_LARGE


# ── Pydantic serialization round-trip for Reservation ─────────────────────────

def test_reservation_round_trip() -> None:
    r = Reservation(
        id=uuid4(),
        reference="RES1234567",
        customer_id=uuid4(),
        date=_tomorrow(),
        time=time(20, 30),
        party_size=3,
        name="Bob",
        phone="+96170000001",
        seating_preference=SeatingPreference.OUTDOOR_NON_TERRACE,
        state=ReservationState.ACTIVE,
        language=Language.AR_LB,
    )
    dumped = r.model_dump(mode="json")
    restored = Reservation.model_validate(dumped)
    assert restored.reference == r.reference
    assert restored.seating_preference == r.seating_preference
    assert restored.state == r.state
    assert restored.language == r.language
    assert restored.party_size == r.party_size


def test_reservation_json_serialization() -> None:
    r = Reservation(
        id=uuid4(),
        reference="RES9ABCDEF",
        customer_id=uuid4(),
        date=_tomorrow(),
        time=time(12, 0),
        party_size=2,
        name="Carol",
        phone="+96176543210",
        seating_preference=SeatingPreference.INDOOR_SMOKING,
        state=ReservationState.ACTIVE,
        language=Language.EN,
    )
    raw = r.model_dump_json()
    assert isinstance(raw, str)
    parsed = json.loads(raw)
    assert parsed["reference"] == "RES9ABCDEF"
    assert parsed["seating_preference"] == "indoor_smoking"
    assert parsed["state"] == "active"


# ── ReservationDraft party_size validator ─────────────────────────────────────

def test_draft_party_size_zero_rejected() -> None:
    with pytest.raises(Exception):
        ReservationDraft(customer_id=uuid4(), party_size=0)


def test_draft_party_size_negative_rejected() -> None:
    with pytest.raises(Exception):
        ReservationDraft(customer_id=uuid4(), party_size=-1)
