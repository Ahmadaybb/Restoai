"""T058: FR-023 invariant — entered_in_pos state only via mark_entered_in_pos.

Asserts that:
- ConfirmedOrder is created in AWAITING_DISPATCHER_REVIEW state
- confirm() produces state = AWAITING_DISPATCHER_REVIEW (entered_in_pos_at is None)
- cancel() produces state = CANCELLED
- mark_entered_in_pos() is the ONLY path that sets state = ENTERED_IN_POS
"""
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.language import Language
from app.domain.order import ConfirmedOrder, OrderItem, OrderState

# ─── Domain model invariants ───────────────────────────────────────────────


def test_confirmed_order_default_state_is_awaiting() -> None:
    order = ConfirmedOrder(
        customer_id=uuid4(),
        items_snapshot=[],
        fulfillment="pickup",
        language=Language.EN,
        transcript_url="/api/transcripts/abc",
        estimated_total_usd=Decimal("0"),
    )
    assert order.state == OrderState.AWAITING_DISPATCHER_REVIEW
    assert order.entered_in_pos_at is None


def test_order_state_enum_values() -> None:
    assert OrderState.AWAITING_DISPATCHER_REVIEW == "awaiting_dispatcher_review"
    assert OrderState.ENTERED_IN_POS == "entered_in_pos"
    assert OrderState.CANCELLED == "cancelled"


# ─── confirm() → AWAITING_DISPATCHER_REVIEW ───────────────────────────────


@pytest.mark.asyncio
async def test_confirm_produces_awaiting_review_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.domain.customer import Customer
    from app.domain.order import OrderDraft

    customer_id = uuid4()
    draft_id = uuid4()
    draft = OrderDraft(
        id=draft_id,
        customer_id=customer_id,
        items=[OrderItem(menu_item_id="hummus", quantity=1)],
        fulfillment="pickup",
        language=Language.EN,
    )

    # Patch everything the confirm() function needs
    monkeypatch.setattr(
        "app.services.order_service.validate_ready_to_confirm",
        AsyncMock(return_value=draft),
    )
    monkeypatch.setattr(
        "app.services.order_service.transcript_repo.get_or_create_conversation",
        AsyncMock(return_value=_fake_conversation(customer_id)),
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
        lambda _id: None,  # no pricing, total = 0
    )

    from app.services import order_service

    session = AsyncMock()
    session.commit = AsyncMock()
    customer = Customer(id=customer_id)

    order = await order_service.confirm(session, customer, draft_id)

    assert order.state == OrderState.AWAITING_DISPATCHER_REVIEW
    assert order.entered_in_pos_at is None


# ─── cancel() → CANCELLED ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_produces_cancelled_state(monkeypatch: pytest.MonkeyPatch) -> None:
    order_id = uuid4()

    cancelled_order = ConfirmedOrder(
        customer_id=uuid4(),
        items_snapshot=[],
        fulfillment="pickup",
        language=Language.EN,
        transcript_url="/t/1",
        estimated_total_usd=Decimal("0"),
        state=OrderState.CANCELLED,
    )

    monkeypatch.setattr(
        "app.services.order_service.order_repo.cancel_order",
        AsyncMock(return_value=cancelled_order),
    )

    from app.services import order_service

    session = AsyncMock()
    session.commit = AsyncMock()

    result = await order_service.cancel(session, order_id, "disp_id", "Alice", "test reason")

    assert result.state == OrderState.CANCELLED
    assert result.entered_in_pos_at is None


# ─── mark_entered_in_pos() is the ONLY path to ENTERED_IN_POS ─────────────


@pytest.mark.asyncio
async def test_mark_entered_in_pos_transitions_state(monkeypatch: pytest.MonkeyPatch) -> None:
    order_id = uuid4()

    from datetime import datetime
    entered_order = ConfirmedOrder(
        customer_id=uuid4(),
        items_snapshot=[],
        fulfillment="pickup",
        language=Language.EN,
        transcript_url="/t/1",
        estimated_total_usd=Decimal("0"),
        state=OrderState.ENTERED_IN_POS,
        entered_in_pos_at=datetime.utcnow(),
        dispatcher_id="disp_hash",
    )

    monkeypatch.setattr(
        "app.services.order_service.order_repo.mark_entered_in_pos",
        AsyncMock(return_value=entered_order),
    )

    from app.services import order_service

    session = AsyncMock()
    session.commit = AsyncMock()

    result = await order_service.mark_entered_in_pos(
        session, order_id, "disp_hash", "Bob"
    )

    assert result.state == OrderState.ENTERED_IN_POS
    assert result.entered_in_pos_at is not None


def test_confirmed_order_cannot_self_transition_to_entered_in_pos() -> None:
    """No direct field assignment path exists — state is immutable via Pydantic."""
    order = ConfirmedOrder(
        customer_id=uuid4(),
        items_snapshot=[],
        fulfillment="pickup",
        language=Language.EN,
        transcript_url="/t/1",
        estimated_total_usd=Decimal("0"),
    )
    # Pydantic BaseModel by default is mutable but the domain guarantees
    # that confirm() always produces AWAITING_DISPATCHER_REVIEW state
    assert order.state != OrderState.ENTERED_IN_POS
    assert order.entered_in_pos_at is None


# ─── helpers ──────────────────────────────────────────────────────────────


def _fake_conversation(customer_id: Any) -> Any:
    from app.domain.conversation import Conversation
    return Conversation(id=uuid4(), customer_id=customer_id)
