"""T070: Graceful degradation tests for FR-034.

Simulates Groq failure and Redis disconnection.
Asserts:
- Localized degradation message returned (not a stack trace)
- ExternalDependencyError caught and not re-raised to caller
- No PII or stack trace in the degradation reply
"""
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.conversation import Conversation
from app.domain.customer import Customer
from app.domain.errors import ExternalDependencyError
from app.domain.language import Intent


class _FakeMessenger:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_message(self, *, chat_id: int, text: str, buttons: Any = None) -> None:
        self.sent.append(text)

    async def send_contact_request(self, *, chat_id: int) -> None:
        pass


_CUSTOMER_ID = uuid4()
_CONV_ID = uuid4()


def _customer() -> Customer:
    return Customer(id=_CUSTOMER_ID)


def _conversation() -> Conversation:
    return Conversation(id=_CONV_ID, customer_id=_CUSTOMER_ID)


# ─── Groq failure ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_groq_failure_returns_degradation_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import conversation_service

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
        lambda _text: (Intent.ORDER, 0.9),
    )
    # parse_order raises ExternalDependencyError to simulate Groq failure
    monkeypatch.setattr(
        "app.services.conversation_service.parse_order_tool",
        type("M", (), {
            "parse_order": AsyncMock(
                side_effect=ExternalDependencyError("groq", "connection timeout")
            )
        })(),
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
    messenger = _FakeMessenger()

    # Must NOT raise — degradation catches and replies
    await conversation_service.handle_text(
        session=session,
        customer=_customer(),
        telegram_chat_id=999,
        text="I want shawarma",
        messenger=messenger,
        llm=None,  # type: ignore[arg-type]
    )

    assert len(messenger.sent) == 1
    reply = messenger.sent[0]
    _assert_is_degradation_message(reply)


@pytest.mark.asyncio
async def test_groq_failure_in_arabic_returns_arabic_degradation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import conversation_service

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
        lambda _text: (Intent.ORDER, 0.9),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.parse_order_tool",
        type("M", (), {
            "parse_order": AsyncMock(
                side_effect=ExternalDependencyError("groq", "error")
            )
        })(),
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
    messenger = _FakeMessenger()

    await conversation_service.handle_text(
        session=session,
        customer=_customer(),
        telegram_chat_id=1,
        text="أريد شاورما",  # Arabic text → reply in AR_LB
        messenger=messenger,
        llm=None,  # type: ignore[arg-type]
    )

    assert len(messenger.sent) == 1
    reply = messenger.sent[0]
    # Arabic reply should contain Arabic text
    assert any(ord(c) > 0x600 for c in reply), "Expected Arabic characters in degradation reply"


# ─── Redis failure ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_redis_failure_returns_degradation_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import conversation_service

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
        lambda _text: (Intent.ORDER, 0.9),
    )

    # parse_order works, but order_draft_service.add_items raises on Redis failure
    from app.domain.order import OrderItem
    from app.domain.tools import ParseOrderOut

    monkeypatch.setattr(
        "app.services.conversation_service.parse_order_tool",
        type("M", (), {
            "parse_order": AsyncMock(
                return_value=ParseOrderOut(
                    items=[OrderItem(menu_item_id="hummus", quantity=1)],
                    unresolved=[],
                    confidence=1.0,
                )
            )
        })(),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.match_dish_tool",
        type("M", (), {"match_dish": AsyncMock()})(),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.order_draft_service",
        type("M", (), {
            "add_items": AsyncMock(
                side_effect=ExternalDependencyError("redis", "connection refused")
            ),
            "get_draft": AsyncMock(return_value=None),
        })(),
    )
    monkeypatch.setattr("app.infra.draft_store.reset_failcount", AsyncMock())
    monkeypatch.setattr("app.infra.draft_store.incr_failcount", AsyncMock(return_value=1))

    session = AsyncMock()
    session.commit = AsyncMock()
    messenger = _FakeMessenger()

    await conversation_service.handle_text(
        session=session,
        customer=_customer(),
        telegram_chat_id=2,
        text="I want hummus",
        messenger=messenger,
        llm=None,  # type: ignore[arg-type]
    )

    assert len(messenger.sent) == 1
    _assert_is_degradation_message(messenger.sent[0])


# ─── No stack trace in reply ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_degradation_reply_contains_no_stack_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import conversation_service

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
        lambda _text: (Intent.ORDER, 0.9),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.parse_order_tool",
        type("M", (), {
            "parse_order": AsyncMock(
                side_effect=ExternalDependencyError("groq", "RuntimeError at line 42")
            )
        })(),
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
    messenger = _FakeMessenger()

    await conversation_service.handle_text(
        session=session,
        customer=_customer(),
        telegram_chat_id=3,
        text="1 hummus",
        messenger=messenger,
        llm=None,  # type: ignore[arg-type]
    )

    reply = messenger.sent[0]
    assert "Traceback" not in reply
    assert "RuntimeError" not in reply
    assert "line 42" not in reply


# ─── helpers ──────────────────────────────────────────────────────────────────


def _assert_is_degradation_message(text: str) -> None:
    """Degradation message must contain a user-facing retry suggestion."""
    text_lower = text.lower()
    has_retry = (
        "try again" in text_lower
        or "مرة" in text
        or "jrreb" in text_lower
        or "technical" in text_lower
        or "مشكلة" in text
        or "آسف" in text
        or "sorry" in text_lower
    )
    assert has_retry, f"Expected degradation message, got: {text!r}"
