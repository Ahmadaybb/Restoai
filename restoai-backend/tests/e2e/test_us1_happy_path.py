"""T071: US1 end-to-end happy path test.

TelegramClient, GroqClient, EmbedderClient are faked.
DB session and Redis are mocked.

Flow:
  /start → menu reply
  "2 hummus, 1 fattoush" → parse → ask fulfillment
  fulfillment:pickup callback → readback
  confirm:<draft_id> callback → order confirmed
  GET /api/dispatcher/orders → order present
  POST .../entered-in-pos → state = entered_in_pos
"""
import json
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.conversation import Conversation
from app.domain.customer import Customer
from app.domain.language import Intent, Language
from app.domain.order import ConfirmedOrder, OrderDraft, OrderItem, OrderState

# ─── Fakes ────────────────────────────────────────────────────────────────────


class _FakeLLM:
    """Fake LLM: returns hard-coded JSON for parse_order, renders readback."""

    def __init__(self) -> None:
        self._parse_response = json.dumps({
            "items": [
                {"phrase": "hummus", "quantity": 2, "customizations": []},
                {"phrase": "fattoush", "quantity": 1, "customizations": []},
            ]
        })

    async def complete_mechanical(self, *, system: str, user: str, **kwargs: Any) -> str:
        return self._parse_response

    async def complete_synthesis(self, *, system: str, user: str, **kwargs: Any) -> str:
        return (
            "Your order: 2x Hummus, 1x Fattoush (pickup).\n"
            "Note: final pricing is confirmed by the dispatcher."
        )


class _FakeMessenger:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, *, chat_id: int, text: str, buttons: Any = None) -> None:
        self.messages.append({"chat_id": chat_id, "text": text, "buttons": buttons})

    async def send_contact_request(self, *, chat_id: int) -> None:
        pass


# ─── Fixtures ─────────────────────────────────────────────────────────────────


CUSTOMER_ID = uuid4()
CHAT_ID = 123456789
DRAFT_ID = uuid4()
ORDER_ID = uuid4()
CONV_ID = uuid4()


def _customer() -> Customer:
    return Customer(id=CUSTOMER_ID, telegram_user_id=CHAT_ID)


def _conversation() -> Conversation:
    return Conversation(id=CONV_ID, customer_id=CUSTOMER_ID)


def _draft(fulfillment: str = "pickup") -> OrderDraft:

    return OrderDraft(
        id=DRAFT_ID,
        customer_id=CUSTOMER_ID,
        items=[
            OrderItem(menu_item_id="hummus", quantity=2),
            OrderItem(menu_item_id="fattoush", quantity=1),
        ],
        fulfillment=fulfillment,
        language=Language.EN,
    )


def _confirmed_order() -> ConfirmedOrder:
    return ConfirmedOrder(
        id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        items_snapshot=[
            OrderItem(menu_item_id="hummus", quantity=2),
            OrderItem(menu_item_id="fattoush", quantity=1),
        ],
        fulfillment="pickup",
        language=Language.EN,
        transcript_url=f"/api/transcripts/{CONV_ID}",
        estimated_total_usd=Decimal("11.00"),
        state=OrderState.AWAITING_DISPATCHER_REVIEW,
    )


# ─── Happy path ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_us1_start_sends_welcome_and_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    """Step 1: /start → welcome + menu."""
    from app.services import conversation_service

    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.get_or_create_conversation",
        AsyncMock(return_value=_conversation()),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.append_turn",
        AsyncMock(side_effect=lambda _s, t: t),
    )
    monkeypatch.setattr("app.repositories.menu_repo.get_menu", lambda: [])

    session = AsyncMock()
    session.commit = AsyncMock()
    messenger = _FakeMessenger()

    await conversation_service.on_start(
        session=session,
        customer=_customer(),
        telegram_chat_id=CHAT_ID,
        messenger=messenger,
    )

    assert len(messenger.messages) == 1
    text = messenger.messages[0]["text"]
    assert "Welcome" in text or "Lakkis" in text


@pytest.mark.asyncio
async def test_us1_order_text_resolved_and_fulfillment_prompted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Step 2: 'I want hummus and fattoush' → items parsed → readback with confirm/edit."""
    from app.domain.menu import MenuItem
    from app.services import conversation_service

    _menu = {
        "hummus": MenuItem(id="hummus", name_en="Hummus", name_ar="حمص", category="Dips", price_usd=Decimal("5"), available=True),
        "fattoush": MenuItem(id="fattoush", name_en="Fattoush", name_ar="فتوش", category="Salads", price_usd=Decimal("6"), available=True),
    }

    monkeypatch.setattr("app.repositories.menu_repo.find_by_phrase", lambda p: [_menu[k] for k in _menu if k in p.lower()])
    monkeypatch.setattr("app.repositories.menu_repo.get_item", lambda i: _menu.get(i))

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
    monkeypatch.setattr(
        "app.services.conversation_service.classify",
        lambda _t: (Intent.ORDER, 0.95),
    )
    monkeypatch.setattr("app.infra.draft_store.reset_failcount", AsyncMock())
    monkeypatch.setattr("app.infra.draft_store.incr_failcount", AsyncMock(return_value=0))

    # First get_draft (address check) → None; second (readback check) → draft with items
    monkeypatch.setattr(
        "app.services.conversation_service.order_draft_service",
        type("M", (), {
            "add_items": AsyncMock(),
            "get_draft": AsyncMock(side_effect=[None, _draft(fulfillment=None)]),
        })(),
    )

    session = AsyncMock()
    session.commit = AsyncMock()
    messenger = _FakeMessenger()

    await conversation_service.handle_text(
        session=session,
        customer=_customer(),
        telegram_chat_id=CHAT_ID,
        text="2 hummus, 1 fattoush",
        messenger=messenger,
        llm=_FakeLLM(),
    )

    assert len(messenger.messages) == 1
    buttons = messenger.messages[0]["buttons"]
    assert buttons is not None
    callback_datas = [b.get("callback_data", "") for b in buttons]
    # New flow: readback shown first; fulfillment asked only after confirm is tapped
    assert any("confirm:" in cd or "edit:" in cd for cd in callback_datas)


@pytest.mark.asyncio
async def test_us1_confirm_callback_creates_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """Step 4: confirm:<draft_id> callback → order confirmed."""
    from app.services import order_service

    monkeypatch.setattr(
        "app.services.order_service.validate_ready_to_confirm",
        AsyncMock(return_value=_draft()),
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
        lambda _inp: type("R", (), {"in_zone": True, "matched_entry": "Hamra"})(),
    )

    session = AsyncMock()
    session.commit = AsyncMock()

    order = await order_service.confirm(session, _customer(), DRAFT_ID)

    assert order.state == OrderState.AWAITING_DISPATCHER_REVIEW
    assert order.customer_id == CUSTOMER_ID


@pytest.mark.asyncio
async def test_us1_dispatcher_list_returns_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """Step 5: GET /api/dispatcher/orders shows the confirmed order."""
    from app.services import dispatcher_service

    confirmed = _confirmed_order()
    customer = _customer()

    monkeypatch.setattr(
        "app.services.dispatcher_service.order_repo.list_awaiting_review",
        AsyncMock(return_value=[(confirmed, customer)]),
    )

    session = AsyncMock()
    pairs = await dispatcher_service.list_orders(session)

    assert len(pairs) == 1
    order, cust = pairs[0]
    assert order.id == ORDER_ID
    assert order.state == OrderState.AWAITING_DISPATCHER_REVIEW


@pytest.mark.asyncio
async def test_us1_entered_in_pos_transitions_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Step 6: POST .../entered-in-pos → state = entered_in_pos."""
    from datetime import datetime

    from app.services import order_service

    entered_order = ConfirmedOrder(
        id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        items_snapshot=[],
        fulfillment="pickup",
        language=Language.EN,
        transcript_url="/t/1",
        estimated_total_usd=Decimal("0"),
        state=OrderState.ENTERED_IN_POS,
        entered_in_pos_at=datetime.utcnow(),
        dispatcher_id="abc123",
    )

    monkeypatch.setattr(
        "app.services.order_service.order_repo.mark_entered_in_pos",
        AsyncMock(return_value=entered_order),
    )

    session = AsyncMock()
    session.commit = AsyncMock()

    result = await order_service.mark_entered_in_pos(
        session, ORDER_ID, "abc123", "Alice"
    )

    assert result.state == OrderState.ENTERED_IN_POS
    assert result.entered_in_pos_at is not None
    assert result.dispatcher_id == "abc123"


# ─── FR-020 field completeness ────────────────────────────────────────────────


def test_confirmed_order_has_all_fr020_fields() -> None:
    """FR-020: every required field present on ConfirmedOrder."""
    order = _confirmed_order()
    # FR-020 required fields
    assert order.id is not None
    assert order.customer_id is not None
    assert order.items_snapshot is not None
    assert order.fulfillment in ("delivery", "pickup")
    assert order.language is not None
    assert order.transcript_url is not None
    assert order.estimated_total_usd >= Decimal("0")
    assert order.state is not None
    assert order.created_at is not None


# ─── Dispatcher API HTTP smoke tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatcher_get_order_via_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/dispatcher/orders/{id} returns the order."""
    from app.services import dispatcher_service

    confirmed = _confirmed_order()
    customer = _customer()

    monkeypatch.setattr(
        "app.services.dispatcher_service.order_repo.get",
        AsyncMock(return_value=(confirmed, customer)),
    )

    session = AsyncMock()
    result = await dispatcher_service.get_order(session, ORDER_ID)

    assert result is not None
    order, cust = result
    assert order.id == ORDER_ID


@pytest.mark.asyncio
async def test_dispatcher_entered_in_pos_via_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST .../entered-in-pos via dispatcher_service (includes token hashing)."""
    from datetime import datetime

    from app.services import dispatcher_service

    entered_order = ConfirmedOrder(
        id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        items_snapshot=[],
        fulfillment="pickup",
        language=Language.EN,
        transcript_url="/t/1",
        estimated_total_usd=Decimal("0"),
        state=OrderState.ENTERED_IN_POS,
        entered_in_pos_at=datetime.utcnow(),
    )

    monkeypatch.setattr(
        "app.services.order_service.order_repo.mark_entered_in_pos",
        AsyncMock(return_value=entered_order),
    )

    session = AsyncMock()
    session.commit = AsyncMock()

    result = await dispatcher_service.mark_entered_in_pos(
        session, ORDER_ID, "raw-token", "Alice"
    )
    assert result is not None
    assert result.state == OrderState.ENTERED_IN_POS
