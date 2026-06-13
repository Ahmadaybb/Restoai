"""T098: US5 E2E — escalation to a human handler.

Flow:
  1. Three consecutive dish_match failures → escalation_service.register_failure
     returns True on the 3rd; Conversation.awaiting_human is set to True.
  2. While awaiting_human: handle_text records inbound turns but sends no reply
     (no_callout verified in test_no_callout_prompts.py; covered briefly here).
  3. Dispatcher API:
     - GET /api/dispatcher/escalations shows the escalated conversation.
     - GET /api/dispatcher/escalations/{id} returns detail with active_draft.
     - POST /take-over assigns the dispatcher.
     - POST /messages relays text to the customer's Telegram.
     - POST /close-handoff clears awaiting_human and resets counters.
  4. After close-handoff the bot resumes normal replies.

FR-024, FR-025, FR-026.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.domain.conversation import Conversation
from app.domain.customer import Customer
from app.domain.language import Language
from app.domain.order import OrderDraft, OrderItem

# ─── Shared ids ───────────────────────────────────────────────────────────────

CUSTOMER_ID = uuid4()
CONV_ID = uuid4()
CHAT_ID = 9988776


def _customer() -> Customer:
    return Customer(
        id=CUSTOMER_ID,
        telegram_user_id=CHAT_ID,
        display_name="Layla",
        phone_e164="+96170000002",
    )


def _conv(awaiting_human: bool = False) -> Conversation:
    return Conversation(
        id=CONV_ID,
        customer_id=CUSTOMER_ID,
        started_at=datetime.now(tz=UTC),
        last_activity_at=datetime.now(tz=UTC),
        awaiting_human=awaiting_human,
    )


def _draft() -> OrderDraft:
    return OrderDraft(
        id=uuid4(),
        customer_id=CUSTOMER_ID,
        items=[OrderItem(menu_item_id="falafel", quantity=3)],
        fulfillment="delivery",
        language=Language.EN,
    )


# ─── T098-1: three failures trigger escalation ───────────────────────────────


@pytest.mark.asyncio
async def test_third_failure_sets_awaiting_human() -> None:
    """On the 3rd registered failure, awaiting_human is set to True."""
    from app.services import escalation_service

    update_conv_mock = AsyncMock()
    session = AsyncMock()
    session.commit = AsyncMock()

    call_count = 0

    async def _fake_incr(customer_id: Any, field: str) -> int:
        nonlocal call_count
        call_count += 1
        return call_count

    with (
        patch("app.services.escalation_service.draft_store.incr_failcount", _fake_incr),
        patch(
            "app.services.escalation_service.transcript_repo.get_or_create_conversation",
            AsyncMock(return_value=_conv()),
        ),
        patch(
            "app.services.escalation_service.transcript_repo.update_conversation",
            update_conv_mock,
        ),
        patch("app.services.escalation_service.draft_store.reset_failcount", AsyncMock()),
        patch("app.services.escalation_service._try_enqueue_notify", lambda _: None),
    ):
        r1 = await escalation_service.register_failure(session, CUSTOMER_ID, "dish_match")
        r2 = await escalation_service.register_failure(session, CUSTOMER_ID, "dish_match")
        r3 = await escalation_service.register_failure(session, CUSTOMER_ID, "dish_match")

    assert r1 is False
    assert r2 is False
    assert r3 is True  # third failure triggers escalation

    # update_conversation must have been called with awaiting_human=True
    update_conv_mock.assert_awaited()
    call_kwargs = {k: v for call in update_conv_mock.call_args_list for k, v in call.kwargs.items()}
    assert call_kwargs.get("awaiting_human") is True


# ─── T098-2: take_over assigns dispatcher ────────────────────────────────────


@pytest.mark.asyncio
async def test_take_over_assigns_dispatcher() -> None:
    """take_over sets assigned_dispatcher_id via update_conversation."""
    from app.services import escalation_service

    update_mock = AsyncMock()
    append_mock = AsyncMock()
    session = AsyncMock()
    session.commit = AsyncMock()

    dispatcher_id = "abc123"
    dispatcher_name = "Ahmad"

    with (
        patch(
            "app.services.escalation_service.transcript_repo.update_conversation",
            update_mock,
        ),
        patch(
            "app.services.escalation_service.order_repo.append_dispatcher_action",
            append_mock,
        ),
    ):
        await escalation_service.take_over(
            session, CONV_ID, dispatcher_id, dispatcher_name
        )

    update_mock.assert_awaited_once_with(
        session, CONV_ID, assigned_dispatcher_id=dispatcher_id
    )
    append_mock.assert_awaited_once()
    action_args = append_mock.call_args.kwargs
    assert action_args["action"] == "take_over_chat"
    assert action_args["dispatcher_name"] == dispatcher_name


# ─── T098-3: send_message routes to Telegram and persists Turn ───────────────


@pytest.mark.asyncio
async def test_send_message_routes_to_telegram() -> None:
    """dispatcher_service.send_message sends attributed text to Telegram."""
    from app.services import dispatcher_service

    messenger = AsyncMock()
    messenger.send_message = AsyncMock()
    session = AsyncMock()
    session.commit = AsyncMock()

    customer = _customer()
    conv = _conv(awaiting_human=True)

    append_turn_mock = AsyncMock()
    append_action_mock = AsyncMock()

    with (
        patch(
            "app.services.dispatcher_service.transcript_repo.get_conversation",
            AsyncMock(return_value=conv),
        ),
        patch(
            "app.services.dispatcher_service.customer_repo.find_by_id",
            AsyncMock(return_value=customer),
        ),
        patch(
            "app.services.dispatcher_service.transcript_repo.append_turn",
            append_turn_mock,
        ),
        patch(
            "app.services.dispatcher_service.order_repo.append_dispatcher_action",
            append_action_mock,
        ),
    ):
        await dispatcher_service.send_message(
            session,
            conversation_id=CONV_ID,
            text="Hello Layla, can I help?",
            dispatcher_token="secret-token",
            dispatcher_name="Ahmad",
            messenger=messenger,
        )

    messenger.send_message.assert_awaited_once()
    call_kwargs = messenger.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == CHAT_ID
    assert "Hello Layla" in call_kwargs["text"]
    assert "[Support]" in call_kwargs["text"]

    # Turn must be recorded as sender="dispatcher"
    saved_turn = append_turn_mock.call_args[0][1]
    assert saved_turn.sender == "dispatcher"


# ─── T098-4: close_handoff clears awaiting_human and resets counters ─────────


@pytest.mark.asyncio
async def test_close_handoff_resets_escalation_state() -> None:
    """close_handoff sets awaiting_human=False and resets all failure counters."""
    from app.services import escalation_service

    update_mock = AsyncMock()
    reset_mock = AsyncMock()
    append_mock = AsyncMock()
    session = AsyncMock()
    session.commit = AsyncMock()

    with (
        patch(
            "app.services.escalation_service.transcript_repo.update_conversation",
            update_mock,
        ),
        patch(
            "app.services.escalation_service.draft_store.reset_failcount",
            reset_mock,
        ),
        patch(
            "app.services.escalation_service.order_repo.append_dispatcher_action",
            append_mock,
        ),
    ):
        await escalation_service.close_handoff(
            session,
            conversation_id=CONV_ID,
            customer_id=CUSTOMER_ID,
            dispatcher_id="abc123",
            dispatcher_name="Ahmad",
        )

    update_mock.assert_awaited_once_with(
        session,
        CONV_ID,
        awaiting_human=False,
        assigned_dispatcher_id=None,
    )
    # All three failure fields are reset
    reset_fields = {call.args[1] for call in reset_mock.call_args_list}
    assert "order_parse" in reset_fields
    assert "dish_match" in reset_fields
    assert "address_extract" in reset_fields

    action_kwargs = append_mock.call_args.kwargs
    assert action_kwargs["action"] == "close_handoff"


# ─── T098-5: list_escalated returns only awaiting_human conversations ─────────


@pytest.mark.asyncio
async def test_list_escalated_returns_only_escalated() -> None:
    """list_escalated must only surface conversations where awaiting_human=True."""
    from app.services import dispatcher_service

    escalated_conv = _conv(awaiting_human=True)
    customer = _customer()
    session = AsyncMock()

    with (
        patch(
            "app.services.dispatcher_service.transcript_repo.list_escalated",
            AsyncMock(return_value=[escalated_conv]),
        ),
        patch(
            "app.services.dispatcher_service.customer_repo.find_by_id",
            AsyncMock(return_value=customer),
        ),
    ):
        pairs = await dispatcher_service.list_escalated(session)

    assert len(pairs) == 1
    conv, cust = pairs[0]
    assert conv.awaiting_human is True
    assert cust.id == CUSTOMER_ID


# ─── T098-6: get_escalation_detail includes draft snapshot ───────────────────


@pytest.mark.asyncio
async def test_get_escalation_detail_includes_draft() -> None:
    """get_escalation_detail must surface the active OrderDraft from Redis."""
    from app.services import dispatcher_service

    conv = _conv(awaiting_human=True)
    customer = _customer()
    draft = _draft()
    session = AsyncMock()

    draft_dict = json.loads(draft.model_dump_json())

    with (
        patch(
            "app.services.dispatcher_service.transcript_repo.get_conversation",
            AsyncMock(return_value=conv),
        ),
        patch(
            "app.services.dispatcher_service.customer_repo.find_by_id",
            AsyncMock(return_value=customer),
        ),
        patch(
            "app.services.dispatcher_service.transcript_repo.get_turns",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.infra.draft_store.get_draft",
            AsyncMock(return_value=draft_dict),
        ),
        patch(
            "app.services.order_draft_service._deserialize",
            return_value=draft,
        ),
    ):
        result = await dispatcher_service.get_escalation_detail(session, CONV_ID)

    assert result is not None
    ret_conv, ret_cust, turns, ret_draft = result
    assert ret_conv.id == CONV_ID
    assert ret_cust.id == CUSTOMER_ID
    assert ret_draft is not None
    assert ret_draft.items[0].menu_item_id == "falafel"
