"""T043 — Cancellation routing when no active reservations.

Verifies:
- When text contains a cancellation keyword and find_active_by_customer returns [],
  _handle_reservation_intent returns the NO_ACTIVE_RESERVATION prompt.
- reservation_service.cancel is NOT called.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.domain.language import Language


@pytest.mark.asyncio
async def test_cancel_routing_no_active_reservations() -> None:
    """cancel intent + no active reservations → NO_ACTIVE_RESERVATION, cancel not called."""
    from app.services import conversation_service, reservation_prompts

    customer_id = uuid4()

    class _FakeCustomer:
        id = customer_id
        display_name = "Test"
        addresses: list = []

    customer = _FakeCustomer()
    session = AsyncMock()
    llm = AsyncMock()
    conv_id = uuid4()

    with (
        patch(
            "app.services.conversation_service.draft_store.get_chat_state",
            AsyncMock(return_value={}),
        ),
        patch(
            "app.services.conversation_service.reservation_service.find_active_by_customer",
            AsyncMock(return_value=[]),
        ) as mock_find,
        patch(
            "app.services.conversation_service.reservation_service.cancel",
            AsyncMock(),
        ) as mock_cancel,
    ):
        text, buttons = await conversation_service._handle_reservation_intent(
            session, customer, "cancel my reservation", Language.EN, llm, conv_id  # type: ignore[arg-type]
        )

    expected = reservation_prompts.NO_ACTIVE_RESERVATION[Language.EN]
    assert text == expected, f"Expected {expected!r}, got {text!r}"
    mock_find.assert_awaited_once()
    mock_cancel.assert_not_awaited()
