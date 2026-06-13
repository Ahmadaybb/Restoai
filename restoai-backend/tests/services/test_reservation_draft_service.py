"""T018 — ReservationDraftService: field collection, prefill, validation.

Tests: (a) collect_field updates correct field and refreshes TTL;
(b) prefill_from_customer sets name + phone from Customer;
(c) validate_ready_to_confirm raises the correct code for each of 9 failure
modes (parametrized); (d) past date raises PAST_DATE; (e) valid draft returns
the draft. Constitution Principle II.
"""
from __future__ import annotations

import datetime as _dt
import json
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.domain.customer import Customer
from app.domain.language import Language
from app.domain.reservation import (
    ReservationDraft,
    ReservationValidationCode,
    ReservationValidationError,
    SeatingPreference,
)
from app.services import reservation_draft_service as svc

# ── fake in-memory store ──────────────────────────────────────────────────────

class _FakeStore:
    """Minimal in-memory replacement for reservation_draft_store."""

    def __init__(self) -> None:
        self._db: dict[str, Any] = {}

    async def get_res_draft(self, customer_id: UUID | str) -> dict[str, Any] | None:
        return self._db.get(str(customer_id))

    async def put_res_draft(
        self, customer_id: UUID | str, draft_dict: dict[str, Any]
    ) -> None:
        # Round-trip through JSON to simulate Redis serialization/deserialization
        self._db[str(customer_id)] = json.loads(json.dumps(draft_dict, default=str))

    async def delete_res_draft(self, customer_id: UUID | str) -> None:
        self._db.pop(str(customer_id), None)


@pytest.fixture
def fake_store(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    store = _FakeStore()
    import app.infra.reservation_draft_store as _rds

    monkeypatch.setattr(_rds, "get_res_draft", store.get_res_draft)
    monkeypatch.setattr(_rds, "put_res_draft", store.put_res_draft)
    monkeypatch.setattr(_rds, "delete_res_draft", store.delete_res_draft)
    return store


# ── helpers ───────────────────────────────────────────────────────────────────

def _tomorrow() -> _dt.date:
    return _dt.datetime.utcnow().date() + timedelta(days=1)


def _yesterday() -> _dt.date:
    return _dt.datetime.utcnow().date() - timedelta(days=1)


async def _make_valid_draft(customer_id: UUID, fake_store: _FakeStore) -> ReservationDraft:
    await svc.start_draft(customer_id, Language.EN)
    await svc.collect_field(customer_id, "date", _tomorrow())
    await svc.collect_field(customer_id, "time", _dt.time(19, 0))
    await svc.collect_field(customer_id, "party_size", 4)
    await svc.collect_field(customer_id, "name", "Alice")
    await svc.collect_field(customer_id, "phone", "+96171234567")
    await svc.collect_field(customer_id, "seating_preference", SeatingPreference.INDOOR_NON_SMOKING)
    return await svc.get_draft(customer_id)  # type: ignore[return-value]


# ── (a) collect_field updates correct field ───────────────────────────────────

@pytest.mark.asyncio
async def test_collect_field_updates_field(fake_store: _FakeStore) -> None:
    customer_id = uuid4()
    await svc.start_draft(customer_id, Language.EN)
    updated = await svc.collect_field(customer_id, "party_size", 6)
    assert updated.party_size == 6

    # Reload from store to confirm persistence
    reloaded = await svc.get_draft(customer_id)
    assert reloaded is not None
    assert reloaded.party_size == 6


@pytest.mark.asyncio
async def test_collect_field_refreshes_ttl(fake_store: _FakeStore) -> None:
    """put_res_draft is called on every collect_field — TTL is always refreshed."""
    customer_id = uuid4()
    await svc.start_draft(customer_id, Language.EN)
    # Verify the store contains the draft after collect_field
    await svc.collect_field(customer_id, "name", "Bob")
    assert str(customer_id) in fake_store._db


# ── (b) prefill_from_customer ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prefill_sets_name_and_phone(fake_store: _FakeStore) -> None:
    customer_id = uuid4()
    await svc.start_draft(customer_id, Language.EN)
    customer = Customer(
        id=customer_id,
        display_name="Carla Jaffall",
        phone_e164="+96176543210",
    )
    draft = await svc.prefill_from_customer(customer_id, customer)
    assert draft.name == "Carla Jaffall"
    assert draft.phone == "+96176543210"


@pytest.mark.asyncio
async def test_prefill_does_not_overwrite_existing_name(fake_store: _FakeStore) -> None:
    customer_id = uuid4()
    await svc.start_draft(customer_id, Language.EN)
    await svc.collect_field(customer_id, "name", "Ahmad")
    customer = Customer(id=customer_id, display_name="Different Name")
    draft = await svc.prefill_from_customer(customer_id, customer)
    assert draft.name == "Ahmad"


# ── (c) validate_ready_to_confirm — 9 failure modes ──────────────────────────

@pytest.mark.parametrize(
    "field,value,expected_code",
    [
        ("date", None, ReservationValidationCode.MISSING_DATE),
        ("time", None, ReservationValidationCode.MISSING_TIME),
        ("party_size", None, ReservationValidationCode.MISSING_PARTY_SIZE),
        ("name", None, ReservationValidationCode.MISSING_NAME),
        ("phone", None, ReservationValidationCode.MISSING_PHONE),
        ("seating_preference", None, ReservationValidationCode.MISSING_SEATING),
    ],
)
@pytest.mark.asyncio
async def test_validate_raises_for_missing_field(
    field: str,
    value: object,
    expected_code: ReservationValidationCode,
    fake_store: _FakeStore,
) -> None:
    customer_id = uuid4()
    await _make_valid_draft(customer_id, fake_store)
    # Overwrite one field to null
    await svc.collect_field(customer_id, field, value)

    with pytest.raises(ReservationValidationError) as exc:
        await svc.validate_ready_to_confirm(customer_id)
    assert exc.value.code == expected_code


# ── (d) past date raises PAST_DATE ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_past_date_raises(fake_store: _FakeStore) -> None:
    customer_id = uuid4()
    await _make_valid_draft(customer_id, fake_store)
    await svc.collect_field(customer_id, "date", _yesterday())

    with pytest.raises(ReservationValidationError) as exc:
        await svc.validate_ready_to_confirm(customer_id)
    assert exc.value.code == ReservationValidationCode.PAST_DATE


# ── terrace too large ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_terrace_too_large_raises(fake_store: _FakeStore) -> None:
    customer_id = uuid4()
    await _make_valid_draft(customer_id, fake_store)
    await svc.collect_field(customer_id, "party_size", 6)
    await svc.collect_field(customer_id, "seating_preference", SeatingPreference.OUTDOOR_TERRACE)

    with pytest.raises(ReservationValidationError) as exc:
        await svc.validate_ready_to_confirm(customer_id)
    assert exc.value.code == ReservationValidationCode.TERRACE_TOO_LARGE


# ── party too large ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_party_too_large_raises(fake_store: _FakeStore) -> None:
    customer_id = uuid4()
    await _make_valid_draft(customer_id, fake_store)
    await svc.collect_field(customer_id, "party_size", 15)

    with pytest.raises(ReservationValidationError) as exc:
        await svc.validate_ready_to_confirm(customer_id)
    assert exc.value.code == ReservationValidationCode.PARTY_TOO_LARGE


# ── (e) valid draft is returned ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_valid_draft_returns_draft(fake_store: _FakeStore) -> None:
    customer_id = uuid4()
    await _make_valid_draft(customer_id, fake_store)
    result = await svc.validate_ready_to_confirm(customer_id)
    assert result is not None
    assert result.party_size == 4
    assert result.name == "Alice"
