"""T096 — While awaiting_human, conversation_service must not reply.

FR-026: once a conversation has awaiting_human=True the bot records
inbound turns but sends no reply to the customer.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.conversation import Conversation
from app.domain.customer import Customer


def _make_customer() -> Customer:
    return Customer(
        id=uuid4(),
        phone_e164=None,
        telegram_user_id=12345,
        display_name="Ahmad",
    )


def _make_conversation(awaiting_human: bool = True) -> Conversation:
    return Conversation(
        id=uuid4(),
        customer_id=uuid4(),
        awaiting_human=awaiting_human,
    )


@pytest.mark.asyncio
async def test_no_reply_when_awaiting_human() -> None:
    """handle_text must not call messenger.send_message when awaiting_human=True."""
    customer = _make_customer()
    conv = _make_conversation(awaiting_human=True)

    mock_session = AsyncMock()
    mock_messenger = AsyncMock()
    mock_llm = AsyncMock()

    from unittest.mock import patch

    import app.repositories.transcript_repo as tr_mod
    import app.services.conversation_service as cs_mod
    import app.services.customer_service as cust_svc_mod
    from app.domain.language import Intent

    with (
        patch.object(tr_mod, "get_or_create_conversation", return_value=conv),
        patch.object(tr_mod, "append_turn", AsyncMock(return_value=None)),
        patch.object(cust_svc_mod, "update_last_seen", AsyncMock(return_value=None)),
        patch("app.services.conversation_service.classify", return_value=(Intent.ORDER, 0.9)),
    ):
        await cs_mod.handle_text(
            session=mock_session,
            customer=customer,
            telegram_chat_id=12345,
            text="I want to order",
            messenger=mock_messenger,
            llm=mock_llm,
        )

    mock_messenger.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_turn_recorded_even_when_awaiting_human() -> None:
    """Inbound turn must still be persisted even when bot is silent (audit trail)."""
    customer = _make_customer()
    conv = _make_conversation(awaiting_human=True)

    mock_session = AsyncMock()
    mock_messenger = AsyncMock()
    mock_llm = AsyncMock()

    from unittest.mock import patch

    import app.repositories.transcript_repo as tr_mod
    import app.services.conversation_service as cs_mod
    import app.services.customer_service as cust_svc_mod
    from app.domain.language import Intent

    append_turn_mock = AsyncMock(return_value=None)

    with (
        patch.object(tr_mod, "get_or_create_conversation", return_value=conv),
        patch.object(tr_mod, "append_turn", append_turn_mock),
        patch.object(cust_svc_mod, "update_last_seen", AsyncMock(return_value=None)),
        patch("app.services.conversation_service.classify", return_value=(Intent.ORDER, 0.9)),
    ):
        await cs_mod.handle_text(
            session=mock_session,
            customer=customer,
            telegram_chat_id=12345,
            text="Hello there",
            messenger=mock_messenger,
            llm=mock_llm,
        )

    # append_turn must have been called once for the inbound turn
    assert append_turn_mock.call_count == 1
    saved_turn = append_turn_mock.call_args[0][1]
    assert saved_turn.sender == "customer"


@pytest.mark.asyncio
async def test_bot_does_reply_when_not_awaiting_human() -> None:
    """When awaiting_human=False and intent=ORDER, bot should send a reply."""
    customer = _make_customer()
    conv = _make_conversation(awaiting_human=False)

    mock_session = AsyncMock()
    mock_messenger = AsyncMock()
    mock_llm = MagicMock()
    mock_llm.complete_mechanical = AsyncMock(
        return_value='{"items": [], "unresolved": [], "confidence": 0.5}'
    )
    mock_llm.complete_synthesis = AsyncMock(return_value="Your order is ready to confirm.")

    from unittest.mock import patch

    import app.infra.draft_store as ds_mod
    import app.repositories.transcript_repo as tr_mod
    import app.services.conversation_service as cs_mod
    import app.services.customer_service as cust_svc_mod
    from app.domain.language import Intent

    with (
        patch.object(tr_mod, "get_or_create_conversation", return_value=conv),
        patch.object(tr_mod, "append_turn", AsyncMock(return_value=None)),
        patch.object(cust_svc_mod, "update_last_seen", AsyncMock(return_value=None)),
        patch("app.services.conversation_service.classify", return_value=(Intent.ORDER, 0.9)),
        patch.object(ds_mod, "incr_failcount", AsyncMock(return_value=0)),
        patch.object(ds_mod, "reset_failcount", AsyncMock(return_value=None)),
        patch.object(ds_mod, "get_draft", AsyncMock(return_value=None)),
        patch("app.services.order_draft_service.add_items", AsyncMock(return_value=None)),
        patch("app.services.order_draft_service.get_draft", AsyncMock(return_value=None)),
    ):
        await cs_mod.handle_text(
            session=mock_session,
            customer=customer,
            telegram_chat_id=12345,
            text="I want a burger",
            messenger=mock_messenger,
            llm=mock_llm,
        )

    mock_messenger.send_message.assert_called()
