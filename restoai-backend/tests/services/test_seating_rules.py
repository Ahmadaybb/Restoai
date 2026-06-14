"""T016 — Seating rules: terrace block (FR-006) and call-centre redirect (FR-007).

Tests call ReservationDraft.validate_ready_to_confirm() directly against
the boundary conditions for _TERRACE_MAX_PARTY (5) and _CALL_CENTER_MAX_PARTY (14).
Constitution Principle II.
"""
from __future__ import annotations

import datetime as _dt
from datetime import timedelta
from uuid import uuid4

import pytest

from app.domain.language import Language
from app.domain.reservation import (
    _CALL_CENTER_MAX_PARTY,
    _TERRACE_MAX_PARTY,
    ReservationDraft,
    ReservationValidationCode,
    ReservationValidationError,
    SeatingPreference,
)


def _tomorrow() -> _dt.date:
    return _dt.datetime.utcnow().date() + timedelta(days=1)


def _base_draft(**overrides: object) -> ReservationDraft:
    defaults: dict[str, object] = dict(
        customer_id=uuid4(),
        date=_tomorrow(),
        time=_dt.time(19, 0),
        party_size=4,
        name="Test User",
        phone="+96171000000",
        seating_preference=SeatingPreference.INDOOR_NON_SMOKING,
        language=Language.EN,
    )
    defaults.update(overrides)
    return ReservationDraft(**defaults)


# ── FR-006: terrace hard-block ────────────────────────────────────────────────

def test_terrace_at_max_party_passes() -> None:
    """Exactly _TERRACE_MAX_PARTY (5) on terrace must NOT raise."""
    draft = _base_draft(
        party_size=_TERRACE_MAX_PARTY,
        seating_preference=SeatingPreference.OUTDOOR_TERRACE,
    )
    draft.validate_ready_to_confirm()  # must not raise


def test_terrace_exceeds_max_party_raises_fr006() -> None:
    """party_size=6 on terrace → TERRACE_TOO_LARGE (FR-006)."""
    draft = _base_draft(
        party_size=_TERRACE_MAX_PARTY + 1,
        seating_preference=SeatingPreference.OUTDOOR_TERRACE,
    )
    with pytest.raises(ReservationValidationError) as exc:
        draft.validate_ready_to_confirm()
    assert exc.value.code == ReservationValidationCode.TERRACE_TOO_LARGE


# ── FR-007: call-centre redirect for >14 ─────────────────────────────────────

def test_party_at_max_allowed_passes() -> None:
    """Exactly _CALL_CENTER_MAX_PARTY (14) must NOT raise."""
    draft = _base_draft(party_size=_CALL_CENTER_MAX_PARTY)
    draft.validate_ready_to_confirm()  # must not raise


def test_party_exceeds_max_allowed_raises_fr007() -> None:
    """party_size=15 → PARTY_TOO_LARGE (FR-007, earliest check)."""
    draft = _base_draft(party_size=_CALL_CENTER_MAX_PARTY + 1)
    with pytest.raises(ReservationValidationError) as exc:
        draft.validate_ready_to_confirm()
    assert exc.value.code == ReservationValidationCode.PARTY_TOO_LARGE


def test_party_too_large_checked_before_terrace_fr006_fr007() -> None:
    """party_size > 14 on terrace raises PARTY_TOO_LARGE, not TERRACE_TOO_LARGE.

    FR-007 must be the earliest check — it blocks collection before seating is
    even evaluated.
    """
    draft = _base_draft(
        party_size=_CALL_CENTER_MAX_PARTY + 1,
        seating_preference=SeatingPreference.OUTDOOR_TERRACE,
    )
    with pytest.raises(ReservationValidationError) as exc:
        draft.validate_ready_to_confirm()
    assert exc.value.code == ReservationValidationCode.PARTY_TOO_LARGE
