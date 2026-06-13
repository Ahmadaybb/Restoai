"""T020 — ReservationService.confirm: reference format, draft deleted, repo called once.

Tests: (a) reference matches ^RES-[A-Z0-9]{7}$; (b) delete_draft called on success;
(c) ReservationValidationError propagated when draft fails validation;
(d) reservation_repo.create called exactly once. Principle II.
"""
from __future__ import annotations

import datetime as _dt
import re
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.language import Language
from app.domain.reservation import (
    Reservation,
    ReservationDraft,
    ReservationState,
    ReservationValidationCode,
    ReservationValidationError,
    SeatingPreference,
)


def _tomorrow() -> _dt.date:
    return _dt.datetime.utcnow().date() + timedelta(days=1)


def _valid_draft() -> ReservationDraft:
    cid = uuid4()
    return ReservationDraft(
        customer_id=cid,
        date=_tomorrow(),
        time=_dt.time(19, 0),
        party_size=4,
        name="Alice",
        phone="+96171234567",
        seating_preference=SeatingPreference.INDOOR_NON_SMOKING,
        language=Language.EN,
    )


# ── (a) reference format ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirm_reference_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reference must match ^RES-[A-Z0-9]{7}$."""
    from app.services import reservation_service

    draft = _valid_draft()
    monkeypatch.setattr(
        "app.services.reservation_service.reservation_draft_service"
        ".validate_ready_to_confirm",
        AsyncMock(return_value=draft),
    )
    captured: list[Reservation] = []

    async def _fake_create(_session: Any, r: Reservation) -> Reservation:
        captured.append(r)
        return r

    monkeypatch.setattr(
        "app.services.reservation_service.reservation_repo.create",
        _fake_create,
    )
    monkeypatch.setattr(
        "app.services.reservation_service.reservation_draft_service.delete_draft",
        AsyncMock(),
    )

    session = AsyncMock()
    result = await reservation_service.confirm(session, draft.customer_id)

    assert re.match(r"^RES-[A-Z0-9]{7}$", result.reference), (
        f"Reference {result.reference!r} does not match ^RES-[A-Z0-9]{{7}}$"
    )


# ── (b) draft deleted on success ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirm_deletes_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    """delete_draft is awaited exactly once after a successful confirm."""
    from app.services import reservation_service

    draft = _valid_draft()
    monkeypatch.setattr(
        "app.services.reservation_service.reservation_draft_service"
        ".validate_ready_to_confirm",
        AsyncMock(return_value=draft),
    )
    monkeypatch.setattr(
        "app.services.reservation_service.reservation_repo.create",
        AsyncMock(side_effect=lambda _s, r: r),
    )
    delete_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.reservation_service.reservation_draft_service.delete_draft",
        delete_mock,
    )

    session = AsyncMock()
    await reservation_service.confirm(session, draft.customer_id)

    delete_mock.assert_awaited_once_with(draft.customer_id)


# ── (c) validation error propagated ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirm_propagates_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ReservationValidationError from validate_ready_to_confirm is re-raised."""
    from app.services import reservation_service

    monkeypatch.setattr(
        "app.services.reservation_service.reservation_draft_service"
        ".validate_ready_to_confirm",
        AsyncMock(
            side_effect=ReservationValidationError(ReservationValidationCode.MISSING_DATE)
        ),
    )

    session = AsyncMock()
    with pytest.raises(ReservationValidationError) as exc:
        await reservation_service.confirm(session, uuid4())

    assert exc.value.code == ReservationValidationCode.MISSING_DATE


# ── (d) repo create called exactly once ──────────────────────────────────────

@pytest.mark.asyncio
async def test_confirm_calls_repo_create_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reservation_repo.create is awaited exactly once per confirm call."""
    from app.services import reservation_service

    draft = _valid_draft()
    monkeypatch.setattr(
        "app.services.reservation_service.reservation_draft_service"
        ".validate_ready_to_confirm",
        AsyncMock(return_value=draft),
    )
    create_mock = AsyncMock(side_effect=lambda _s, r: r)
    monkeypatch.setattr(
        "app.services.reservation_service.reservation_repo.create",
        create_mock,
    )
    monkeypatch.setattr(
        "app.services.reservation_service.reservation_draft_service.delete_draft",
        AsyncMock(),
    )

    session = AsyncMock()
    await reservation_service.confirm(session, draft.customer_id)

    assert create_mock.await_count == 1


# ── T038: ReservationService.modify ──────────────────────────────────────────

def _make_reservation(
    party_size: int = 4,
    seating: SeatingPreference = SeatingPreference.INDOOR_NON_SMOKING,
) -> Reservation:
    return Reservation(
        customer_id=uuid4(),
        reference="RES-ABCDEF1",
        date=_tomorrow(),
        time=_dt.time(19, 0),
        party_size=party_size,
        name="Alice",
        phone="+96171234567",
        seating_preference=seating,
        state=ReservationState.ACTIVE,
        language=Language.EN,
    )


@pytest.mark.asyncio
async def test_modify_updates_date_reference_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(a) modify updates date; reference must be unchanged. T038, FR-013."""
    from app.services import reservation_service

    res = _make_reservation()
    new_date = _tomorrow() + _dt.timedelta(days=7)

    monkeypatch.setattr(
        "app.services.reservation_service.reservation_repo.get_by_id",
        AsyncMock(return_value=res),
    )
    updated = res.model_copy(update={"date": new_date})
    monkeypatch.setattr(
        "app.services.reservation_service.reservation_repo.update_fields",
        AsyncMock(return_value=updated),
    )

    session = AsyncMock()
    result = await reservation_service.modify(
        session, res.customer_id, res.id, {"date": new_date}
    )

    assert result.date == new_date
    assert result.reference == "RES-ABCDEF1"


@pytest.mark.asyncio
async def test_modify_party_size_on_terrace_raises_terrace_too_large(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(b) party_size=6 on OUTDOOR_TERRACE booking raises TERRACE_TOO_LARGE. T038, FR-015."""
    from app.services import reservation_service

    res = _make_reservation(party_size=3, seating=SeatingPreference.OUTDOOR_TERRACE)

    monkeypatch.setattr(
        "app.services.reservation_service.reservation_repo.get_by_id",
        AsyncMock(return_value=res),
    )

    session = AsyncMock()
    with pytest.raises(ReservationValidationError) as exc:
        await reservation_service.modify(
            session, res.customer_id, res.id, {"party_size": 6}
        )

    assert exc.value.code == ReservationValidationCode.TERRACE_TOO_LARGE


@pytest.mark.asyncio
async def test_modify_party_size_on_terrace_within_limit_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(c) party_size=4 on OUTDOOR_TERRACE booking (≤5) succeeds. T038, FR-015."""
    from app.services import reservation_service

    res = _make_reservation(party_size=3, seating=SeatingPreference.OUTDOOR_TERRACE)
    updated = res.model_copy(update={"party_size": 4})

    monkeypatch.setattr(
        "app.services.reservation_service.reservation_repo.get_by_id",
        AsyncMock(return_value=res),
    )
    monkeypatch.setattr(
        "app.services.reservation_service.reservation_repo.update_fields",
        AsyncMock(return_value=updated),
    )

    session = AsyncMock()
    result = await reservation_service.modify(
        session, res.customer_id, res.id, {"party_size": 4}
    )

    assert result.party_size == 4
    assert result.seating_preference == SeatingPreference.OUTDOOR_TERRACE


@pytest.mark.asyncio
async def test_modify_seating_from_terrace_to_indoor_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(d) seating change from OUTDOOR_TERRACE to INDOOR_NON_SMOKING succeeds. T038."""
    from app.services import reservation_service

    res = _make_reservation(party_size=6, seating=SeatingPreference.OUTDOOR_TERRACE)
    updated = res.model_copy(
        update={"seating_preference": SeatingPreference.INDOOR_NON_SMOKING}
    )

    monkeypatch.setattr(
        "app.services.reservation_service.reservation_repo.get_by_id",
        AsyncMock(return_value=res),
    )
    monkeypatch.setattr(
        "app.services.reservation_service.reservation_repo.update_fields",
        AsyncMock(return_value=updated),
    )

    session = AsyncMock()
    result = await reservation_service.modify(
        session, res.customer_id, res.id,
        {"seating_preference": SeatingPreference.INDOOR_NON_SMOKING},
    )

    assert result.seating_preference == SeatingPreference.INDOOR_NON_SMOKING
    assert result.reference == "RES-ABCDEF1"
