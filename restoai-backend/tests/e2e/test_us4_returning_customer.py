"""T090: US4 E2E — returning customer greeted by name and offered saved address.

Flow:
  First chat (new customer):
    /start → welcome without name
    "2 hummus" → items parsed → fulfillment prompt
    fulfillment:delivery (no saved addresses) → plain address prompt
    confirm → order confirmed; profile (name + address) persisted via T089

  Second chat (returning customer — display_name + saved address already in DB):
    /start → welcome includes "Welcome back, Ahmed! 😊"
    "1 fattoush" → items parsed → fulfillment prompt
    fulfillment:delivery (has saved addresses) → one-tap address buttons shown
    saved_address:<addr_id> callback → address attached without re-typing
    confirm → second order confirmed

FR-012, FR-013, FR-014, FR-015.
"""
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.conversation import Conversation
from app.domain.customer import Address, Customer
from app.domain.language import Language
from app.domain.order import ConfirmedOrder, OrderDraft, OrderItem, OrderState

# ─── Shared fixtures ──────────────────────────────────────────────────────────

CUSTOMER_ID = uuid4()
CHAT_ID = 7654321
DRAFT_ID = uuid4()
ORDER_ID = uuid4()
CONV_ID = uuid4()
ADDR_ID = uuid4()


def _new_customer() -> Customer:
    """First-visit customer — anonymous, no name, no addresses."""
    return Customer(
        id=CUSTOMER_ID,
        telegram_user_id=CHAT_ID,
        display_name=None,
    )


def _returning_customer() -> Customer:
    """Second-visit customer — name + one saved address."""
    return Customer(
        id=CUSTOMER_ID,
        telegram_user_id=CHAT_ID,
        display_name="Ahmed",
        phone_e164="+96170000001",
        addresses=[
            Address(
                id=ADDR_ID,
                customer_id=CUSTOMER_ID,
                kind="text",
                text_value="Hamra Street, near AUB",
            )
        ],
    )


def _conversation() -> Conversation:
    return Conversation(
        id=CONV_ID,
        customer_id=CUSTOMER_ID,
        started_at=datetime.now(tz=UTC),
        last_activity_at=datetime.now(tz=UTC),
    )


def _draft_delivery() -> OrderDraft:
    return OrderDraft(
        id=DRAFT_ID,
        customer_id=CUSTOMER_ID,
        items=[OrderItem(menu_item_id="hummus", quantity=2)],
        fulfillment="delivery",
        language=Language.EN,
    )


def _confirmed_order() -> ConfirmedOrder:
    return ConfirmedOrder(
        id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        items_snapshot=[OrderItem(menu_item_id="hummus", quantity=2)],
        fulfillment="delivery",
        language=Language.EN,
        transcript_url=f"/api/transcripts/{CONV_ID}",
        estimated_total_usd=Decimal("14.00"),
        state=OrderState.AWAITING_DISPATCHER_REVIEW,
    )


class _FakeLLM:
    def __init__(self, parse_resp: str = "") -> None:
        self._parse = parse_resp or json.dumps({
            "items": [{"phrase": "hummus", "quantity": 2, "customizations": []}]
        })

    async def complete_mechanical(self, *, system: str, user: str, **kw: Any) -> str:
        return self._parse

    async def complete_synthesis(self, *, system: str, user: str, **kw: Any) -> str:
        return "Your order looks great!"


class _FakeMessenger:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, *, chat_id: int, text: str, buttons: Any = None) -> None:
        self.messages.append({"chat_id": chat_id, "text": text, "buttons": buttons})

    async def send_contact_request(self, *, chat_id: int) -> None:
        pass


# ─── Test 1: on_start greets returning customer by name ───────────────────────


@pytest.mark.asyncio
async def test_on_start_greets_returning_customer_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second chat /start must contain 'Welcome back, Ahmed! 😊'."""
    from app.services import conversation_service

    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.get_or_create_conversation",
        AsyncMock(return_value=_conversation()),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.append_turn",
        AsyncMock(),
    )
    monkeypatch.setattr("app.repositories.menu_repo.get_menu", lambda: [])

    session = AsyncMock()
    session.commit = AsyncMock()
    messenger = _FakeMessenger()

    await conversation_service.on_start(
        session=session,
        customer=_returning_customer(),
        telegram_chat_id=CHAT_ID,
        messenger=messenger,
    )

    assert len(messenger.messages) == 1
    text = messenger.messages[0]["text"]
    assert "Ahmed" in text, f"Expected name 'Ahmed' in greeting, got: {text[:200]}"
    assert "Welcome back" in text


# ─── Test 2: first chat /start has no personalised greeting ───────────────────


@pytest.mark.asyncio
async def test_on_start_new_customer_no_name_in_greeting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First chat /start must NOT contain 'Welcome back' for an anonymous customer."""
    from app.services import conversation_service

    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.get_or_create_conversation",
        AsyncMock(return_value=_conversation()),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.append_turn",
        AsyncMock(),
    )
    monkeypatch.setattr("app.repositories.menu_repo.get_menu", lambda: [])

    session = AsyncMock()
    session.commit = AsyncMock()
    messenger = _FakeMessenger()

    await conversation_service.on_start(
        session=session,
        customer=_new_customer(),
        telegram_chat_id=CHAT_ID,
        messenger=messenger,
    )

    text = messenger.messages[0]["text"]
    assert "Welcome back" not in text


# ─── Test 3: delivery callback shows saved-address buttons ────────────────────


@pytest.mark.asyncio
async def test_delivery_callback_shows_saved_address_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When returning customer picks delivery, one button per saved address + New address."""
    # Test via the router callback path (mocking the app/session/telegram objects)
    from app.api import telegram_router

    messenger = _FakeMessenger()

    # Minimal fake app
    fake_state = type("S", (), {"telegram": messenger, "llm": None, "embedder": None})()
    fake_app = type("A", (), {"state": fake_state})()

    customer = _returning_customer()

    monkeypatch.setattr(
        "app.api.telegram_router.customer_service.get_or_create_anonymous",
        AsyncMock(return_value=customer),
    )
    monkeypatch.setattr(
        "app.api.telegram_router.customer_service.set_display_name",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.api.telegram_router.order_draft_service.set_fulfillment",
        AsyncMock(return_value=_draft_delivery()),
    )

    session = AsyncMock()
    session.commit = AsyncMock()

    update = {
        "callback_query": {
            "from": {"id": CHAT_ID, "first_name": "Ahmed"},
            "message": {"chat": {"id": CHAT_ID}},
            "data": "fulfillment:delivery",
        }
    }

    await telegram_router._process_update(fake_app, session, update)

    assert len(messenger.messages) == 1
    msg = messenger.messages[0]
    buttons = msg["buttons"]
    assert buttons is not None, "Saved-address buttons must be sent"

    callback_datas = [b["callback_data"] for b in buttons]
    # One button for the saved address
    assert any(f"saved_address:{ADDR_ID}" in cd for cd in callback_datas), (
        f"Expected saved_address:{ADDR_ID} in buttons: {callback_datas}"
    )
    # One "New address" button
    assert any(cd == "new_address" for cd in callback_datas), (
        f"Expected 'new_address' button: {callback_datas}"
    )


# ─── Test 4: delivery with no saved addresses shows plain prompt ──────────────


@pytest.mark.asyncio
async def test_delivery_callback_no_saved_addresses_shows_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """New customer picking delivery gets plain 'please share your address' prompt."""
    from app.api import telegram_router

    messenger = _FakeMessenger()
    fake_state = type("S", (), {"telegram": messenger, "llm": None, "embedder": None})()
    fake_app = type("A", (), {"state": fake_state})()

    customer = _new_customer()

    monkeypatch.setattr(
        "app.api.telegram_router.customer_service.get_or_create_anonymous",
        AsyncMock(return_value=customer),
    )
    monkeypatch.setattr(
        "app.api.telegram_router.customer_service.set_display_name",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.api.telegram_router.order_draft_service.set_fulfillment",
        AsyncMock(return_value=_draft_delivery()),
    )

    session = AsyncMock()
    session.commit = AsyncMock()

    update = {
        "callback_query": {
            "from": {"id": CHAT_ID, "first_name": ""},
            "message": {"chat": {"id": CHAT_ID}},
            "data": "fulfillment:delivery",
        }
    }

    await telegram_router._process_update(fake_app, session, update)

    assert len(messenger.messages) == 1
    text = messenger.messages[0]["text"]
    assert "address" in text.lower()
    assert messenger.messages[0]["buttons"] is None


# ─── Test 5: confirm persists profile via persist_on_confirmation (T089) ──────


@pytest.mark.asyncio
async def test_confirm_persists_profile_on_first_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After confirm(), persist_on_confirmation is called with the customer and address."""
    from app.services import order_service

    draft = _draft_delivery()
    draft = draft.model_copy(update={
        "address": Address(
            id=ADDR_ID,
            customer_id=CUSTOMER_ID,
            kind="text",
            text_value="Hamra Street, near AUB",
        )
    })

    monkeypatch.setattr(
        "app.services.order_service.validate_ready_to_confirm",
        AsyncMock(return_value=draft),
    )
    monkeypatch.setattr(
        "app.services.order_service.transcript_repo.get_or_create_conversation",
        AsyncMock(return_value=_conversation()),
    )
    monkeypatch.setattr(
        "app.services.order_service.transcript_repo.update_conversation",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.order_service.order_repo.create_confirmed",
        AsyncMock(side_effect=lambda _s, o: o),
    )
    monkeypatch.setattr(
        "app.services.order_service.draft_store.delete_draft",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.order_service.menu_repo.get_item",
        lambda _id: None,
    )
    monkeypatch.setattr(
        "app.services.order_service.check_zone",
        lambda _inp: type("R", (), {"in_zone": True, "matched_entry": None})(),
    )

    persist_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.order_service.customer_service.persist_on_confirmation",
        persist_mock,
    )

    session = AsyncMock()
    session.commit = AsyncMock()

    customer = _returning_customer()
    order = await order_service.confirm(session, customer, DRAFT_ID)

    assert order.state == OrderState.AWAITING_DISPATCHER_REVIEW

    persist_mock.assert_awaited_once()
    call_args = persist_mock.call_args
    assert call_args.args[1] is customer
    assert call_args.args[2] is not None
    assert call_args.args[2].text_value == "Hamra Street, near AUB"


# ─── Test 6: saved_address callback attaches address to draft ─────────────────


@pytest.mark.asyncio
async def test_saved_address_callback_attaches_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tapping saved_address:<id> callback wires the saved address to the active draft."""
    from app.api import telegram_router

    messenger = _FakeMessenger()
    fake_state = type("S", (), {"telegram": messenger, "llm": None, "embedder": None})()
    fake_app = type("A", (), {"state": fake_state})()

    customer = _returning_customer()
    saved_addr = customer.addresses[0]

    monkeypatch.setattr(
        "app.api.telegram_router.customer_service.get_or_create_anonymous",
        AsyncMock(return_value=customer),
    )
    monkeypatch.setattr(
        "app.api.telegram_router.customer_service.set_display_name",
        AsyncMock(),
    )

    select_mock = AsyncMock()
    monkeypatch.setattr(
        "app.api.telegram_router.order_draft_service.select_saved_address",
        select_mock,
    )

    session = AsyncMock()
    session.commit = AsyncMock()

    update = {
        "callback_query": {
            "from": {"id": CHAT_ID, "first_name": "Ahmed"},
            "message": {"chat": {"id": CHAT_ID}},
            "data": f"saved_address:{ADDR_ID}",
        }
    }

    await telegram_router._process_update(fake_app, session, update)

    select_mock.assert_awaited_once_with(CUSTOMER_ID, saved_addr)

    assert len(messenger.messages) == 1
    assert "Hamra Street" in messenger.messages[0]["text"]
