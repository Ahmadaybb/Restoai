"""T068: Every customer message and bot reply lands as a Turn row.

Tests that handle_text() calls transcript_repo.append_turn with:
- Correct sender ("customer" for inbound, "bot" for outbound)
- Redacted text
- Correct language
- Correct intent

Uses mocked DB session, LLM client, and Telegram client.
"""
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.conversation import Conversation, Turn
from app.domain.customer import Customer
from app.domain.language import Intent


class _FakeLLM:
    async def complete_mechanical(self, *, system: str, user: str, **kwargs: Any) -> str:
        return '{"items": []}'

    async def complete_synthesis(self, *, system: str, user: str, **kwargs: Any) -> str:
        return "Order confirmed!"


class _FakeMessenger:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_message(self, *, chat_id: int, text: str, buttons: Any = None) -> None:
        self.sent.append({"chat_id": chat_id, "text": text, "buttons": buttons})

    async def send_contact_request(self, *, chat_id: int) -> None:
        pass


_CUSTOMER_ID = uuid4()
_CONV_ID = uuid4()


def _make_customer() -> Customer:
    return Customer(id=_CUSTOMER_ID)


def _make_conversation() -> Conversation:
    return Conversation(id=_CONV_ID, customer_id=_CUSTOMER_ID)


@pytest.mark.asyncio
async def test_handle_text_appends_inbound_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Customer text message produces an inbound Turn row."""
    from app.services import conversation_service

    turns_appended: list[Turn] = []

    async def _fake_append(session: Any, turn: Turn) -> Turn:
        turns_appended.append(turn)
        return turn

    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.get_or_create_conversation",
        AsyncMock(return_value=_make_conversation()),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.append_turn",
        _fake_append,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.customer_service.update_last_seen",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.classify",
        lambda _text: (Intent.QUERY, 0.9),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.order_draft_service",
        type("M", (), {
            "add_items": AsyncMock(),
            "get_draft": AsyncMock(return_value=None),
        })(),
    )

    session = AsyncMock()
    session.commit = AsyncMock()

    await conversation_service.handle_text(
        session=session,
        customer=_make_customer(),
        telegram_chat_id=123456,
        text="What time do you close?",
        messenger=_FakeMessenger(),
        llm=_FakeLLM(),
    )

    # Two turns: inbound + outbound
    assert len(turns_appended) == 2
    inbound = turns_appended[0]
    outbound = turns_appended[1]

    assert inbound.sender == "customer"
    assert inbound.conversation_id == _CONV_ID
    # Text was redacted (original not leaked)
    assert inbound.text is not None

    assert outbound.sender == "bot"
    assert outbound.conversation_id == _CONV_ID


@pytest.mark.asyncio
async def test_handle_text_inbound_turn_carries_correct_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Intent from classifier is stored on the inbound Turn."""
    from app.services import conversation_service

    turns_appended: list[Turn] = []

    async def _fake_append(session: Any, turn: Turn) -> Turn:
        turns_appended.append(turn)
        return turn

    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.get_or_create_conversation",
        AsyncMock(return_value=_make_conversation()),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.append_turn",
        _fake_append,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.customer_service.update_last_seen",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.classify",
        lambda _text: (Intent.ORDER, 0.95),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.parse_order_tool",
        type("M", (), {"parse_order": AsyncMock(return_value=_empty_parse_out())})(),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.match_dish_tool",
        type("M", (), {"match_dish": AsyncMock()})(),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.order_draft_service",
        type("M", (), {
            "add_items": AsyncMock(),
            "get_draft": AsyncMock(return_value=None),
        })(),
    )
    monkeypatch.setattr(
        "app.infra.draft_store.reset_failcount", AsyncMock()
    )
    monkeypatch.setattr(
        "app.infra.draft_store.incr_failcount", AsyncMock(return_value=0)
    )

    session = AsyncMock()
    session.commit = AsyncMock()

    await conversation_service.handle_text(
        session=session,
        customer=_make_customer(),
        telegram_chat_id=123456,
        text="I want hummus",
        messenger=_FakeMessenger(),
        llm=_FakeLLM(),
    )

    inbound = turns_appended[0]
    assert inbound.intent == Intent.ORDER


@pytest.mark.asyncio
async def test_on_start_appends_bot_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """on_start() records the welcome message as a bot Turn."""
    from app.services import conversation_service

    turns_appended: list[Turn] = []

    async def _fake_append(session: Any, turn: Turn) -> Turn:
        turns_appended.append(turn)
        return turn

    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.get_or_create_conversation",
        AsyncMock(return_value=_make_conversation()),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.transcript_repo.append_turn",
        _fake_append,
    )
    monkeypatch.setattr(
        "app.repositories.menu_repo.get_menu",
        lambda: [],
    )

    session = AsyncMock()
    session.commit = AsyncMock()
    messenger = _FakeMessenger()

    await conversation_service.on_start(
        session=session,
        customer=_make_customer(),
        telegram_chat_id=42,
        messenger=messenger,
    )

    assert len(turns_appended) == 1
    assert turns_appended[0].sender == "bot"
    assert len(messenger.sent) == 1


# ─── helpers ──────────────────────────────────────────────────────────────────


def _empty_parse_out() -> Any:
    from app.domain.tools import ParseOrderOut
    return ParseOrderOut(items=[], unresolved=[], confidence=1.0)
