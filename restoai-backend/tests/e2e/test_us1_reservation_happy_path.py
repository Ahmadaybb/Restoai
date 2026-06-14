"""T027: US1 reservation happy path — RESERVATION intent → extract → seating → confirm.

Mock Groq + Redis + Postgres.
Asserts: (a) Reservation has all FR-011 fields; (b) reference ^RES-[A-Z0-9]{7}$;
(c) confirmation message sent to Telegram messenger; (d) draft deleted after confirm.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.conversation import Conversation
from app.domain.customer import Customer
from app.domain.language import Intent, Language
from app.domain.reservation import (
    Reservation,
    ReservationDraft,
    SeatingPreference,
)

# ── constants ─────────────────────────────────────────────────────────────────

CUSTOMER_ID = uuid4()
CHAT_ID = 555_000_111
CONV_ID = uuid4()


def _tomorrow() -> _dt.date:
    return _dt.datetime.utcnow().date() + timedelta(days=1)


def _customer() -> Customer:
    return Customer(id=CUSTOMER_ID, telegram_user_id=CHAT_ID)


def _conversation() -> Conversation:
    return Conversation(id=CONV_ID, customer_id=CUSTOMER_ID)


def _complete_draft() -> ReservationDraft:
    return ReservationDraft(
        customer_id=CUSTOMER_ID,
        date=_tomorrow(),
        time=_dt.time(19, 0),
        party_size=4,
        name="Alice Khoury",
        phone="+96171234567",
        seating_preference=SeatingPreference.INDOOR_NON_SMOKING,
        language=Language.EN,
    )


def _draft_no_seating() -> ReservationDraft:
    return ReservationDraft(
        customer_id=CUSTOMER_ID,
        date=_tomorrow(),
        time=_dt.time(19, 0),
        party_size=4,
        name="Alice Khoury",
        phone="+96171234567",
        language=Language.EN,
    )


# ── fake messenger ─────────────────────────────────────────────────────────────

class _FakeMessenger:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_message(
        self, *, chat_id: int, text: str, buttons: Any = None
    ) -> None:
        self.messages.append({"chat_id": chat_id, "text": text, "buttons": buttons})


# ── fake LLM ──────────────────────────────────────────────────────────────────

class _FakeLLM:
    """Returns extracted fields JSON for mechanical, confirmation text for synthesis."""

    def __init__(self, extracted: dict[str, Any] | None = None) -> None:
        self._extracted = extracted or {}

    async def complete_mechanical(self, *, system: str, user: str, **_: Any) -> str:
        return json.dumps(self._extracted)

    async def complete_synthesis(self, *, system: str, user: str, **_: Any) -> str:
        return "✅ Reservation confirmed! Ref: RES-TEST12 on 20 Jun at 7:00 PM for 4."


# ── fake draft store ──────────────────────────────────────────────────────────

class _FakeDraftStore:
    def __init__(self, initial: ReservationDraft | None = None) -> None:
        self._drafts: dict[str, dict[str, Any]] = {}
        self.deleted: list[str] = []
        if initial:
            self._drafts[str(initial.customer_id)] = json.loads(
                json.dumps(initial.model_dump(mode="json"), default=str)
            )

    async def get_res_draft(self, customer_id: Any) -> dict[str, Any] | None:
        return self._drafts.get(str(customer_id))

    async def put_res_draft(self, customer_id: Any, d: dict[str, Any]) -> None:
        self._drafts[str(customer_id)] = json.loads(json.dumps(d, default=str))

    async def delete_res_draft(self, customer_id: Any) -> None:
        self._drafts.pop(str(customer_id), None)
        self.deleted.append(str(customer_id))


# ── shared monkeypatch helper ─────────────────────────────────────────────────

def _patch_common(
    monkeypatch: pytest.MonkeyPatch,
    draft_store_obj: _FakeDraftStore,
    chat_state: dict[str, Any] | None = None,
) -> None:
    import app.infra.reservation_draft_store as _rds

    monkeypatch.setattr(_rds, "get_res_draft", draft_store_obj.get_res_draft)
    monkeypatch.setattr(_rds, "put_res_draft", draft_store_obj.put_res_draft)
    monkeypatch.setattr(_rds, "delete_res_draft", draft_store_obj.delete_res_draft)

    _state: dict[str, Any] = chat_state or {}
    monkeypatch.setattr(
        "app.infra.draft_store.get_chat_state",
        AsyncMock(return_value=_state),
    )
    monkeypatch.setattr(
        "app.infra.draft_store.put_chat_state",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.get_or_create_conversation",
        AsyncMock(return_value=_conversation()),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.append_turn",
        AsyncMock(side_effect=lambda _s, t: t),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.customer_service.update_last_seen",
        AsyncMock(),
    )


# ── Test (a)+(b): Reservation has all FR-011 fields; reference ^RES-[A-Z0-9]{7}$ ──

@pytest.mark.asyncio
async def test_confirmed_reservation_has_all_fr011_fields_and_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(a) Reservation has all 7 FR-011 fields; (b) reference matches ^RES-[A-Z0-9]{7}$."""
    from app.services import reservation_service

    draft = _complete_draft()
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
        "app.services.reservation_service.reservation_repo.create", _fake_create
    )
    monkeypatch.setattr(
        "app.services.reservation_service.reservation_draft_service.delete_draft",
        AsyncMock(),
    )

    session = AsyncMock()
    result = await reservation_service.confirm(session, CUSTOMER_ID)

    # (a) all FR-011 fields present
    assert result.reference
    assert result.date == draft.date
    assert result.time == draft.time
    assert result.party_size == draft.party_size
    assert result.name == "Alice Khoury"
    assert result.phone == "+96171234567"
    assert result.seating_preference == SeatingPreference.INDOOR_NON_SMOKING

    # (b) reference format
    assert re.match(r"^RES-[A-Z0-9]{7}$", result.reference), result.reference


# ── Test (c): Confirmation message sent to Telegram messenger ─────────────────

@pytest.mark.asyncio
async def test_confirmation_message_sent_to_telegram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(c) After seating collected, continue_reservation_flow sends confirmation text."""
    from app.services import conversation_service

    draft_store_obj = _FakeDraftStore(initial=_complete_draft())
    _patch_common(monkeypatch, draft_store_obj)

    captured: list[Reservation] = []

    async def _fake_create(_session: Any, r: Reservation) -> Reservation:
        captured.append(r)
        return r

    monkeypatch.setattr(
        "app.services.reservation_service.reservation_repo.create", _fake_create
    )

    messenger = _FakeMessenger()
    session = AsyncMock()
    session.commit = AsyncMock()

    await conversation_service.continue_reservation_flow(
        session=session,
        customer=_customer(),
        chat_id=CHAT_ID,
        messenger=messenger,
        llm=_FakeLLM(),
        lang=Language.EN,
    )

    assert len(messenger.messages) == 1
    text = messenger.messages[0]["text"]
    assert len(text) > 0


# ── Test (d): Draft deleted after confirmation ────────────────────────────────

@pytest.mark.asyncio
async def test_draft_deleted_after_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    """(d) delete_res_draft is called once the reservation is confirmed."""
    from app.services import conversation_service

    draft_store_obj = _FakeDraftStore(initial=_complete_draft())
    _patch_common(monkeypatch, draft_store_obj)

    async def _fake_create(_session: Any, r: Reservation) -> Reservation:
        return r

    monkeypatch.setattr(
        "app.services.reservation_service.reservation_repo.create", _fake_create
    )

    session = AsyncMock()
    messenger = _FakeMessenger()

    await conversation_service.continue_reservation_flow(
        session=session,
        customer=_customer(),
        chat_id=CHAT_ID,
        messenger=messenger,
        llm=_FakeLLM(),
        lang=Language.EN,
    )

    assert str(CUSTOMER_ID) in draft_store_obj.deleted


# ── Test: RESERVATION intent routes to reservation handler → seating prompt ──

@pytest.mark.asyncio
async def test_reservation_intent_reaches_seating_dialog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RESERVATION intent → extract fields → bot asks for seating (returns buttons)."""
    from app.services import conversation_service

    tomorrow_iso = _tomorrow().isoformat()
    extracted_payload = {
        "date": tomorrow_iso,
        "time": "19:00",
        "party_size": 4,
        "name": "Alice Khoury",
        "phone": "+96171234567",
        "date_is_informal": False,
    }
    draft_store_obj = _FakeDraftStore()
    _patch_common(monkeypatch, draft_store_obj, chat_state={"waiting_for": ""})

    monkeypatch.setattr(
        "app.services.conversation_service.classify",
        lambda _t: (Intent.RESERVATION, 0.92),
    )

    session = AsyncMock()
    session.commit = AsyncMock()
    messenger = _FakeMessenger()

    await conversation_service.handle_text(
        session=session,
        customer=_customer(),
        telegram_chat_id=CHAT_ID,
        text="Table for 4 tomorrow at 7pm, Alice Khoury +96171234567",
        messenger=messenger,
        llm=_FakeLLM(extracted=extracted_payload),
    )

    assert len(messenger.messages) == 1
    buttons = messenger.messages[0]["buttons"]
    # Bot should have asked for seating — indoor/outdoor buttons
    assert buttons is not None
    callback_datas = [b.get("callback_data", "") for b in buttons]
    assert any("res_seating:" in cd for cd in callback_datas)
