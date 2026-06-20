"""Tests for Bug Fix 1 — feedback fires at entered_in_pos, not at confirm().

Two regression guards:
  1. order_service.confirm() must never reference enqueue_feedback_request.
  2. orders.py (dispatcher API) must contain enqueue_feedback_request after entered_in_pos.

Plus a runtime guard that confirm() completes without touching the enqueue path.
"""
import inspect
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.domain.customer import Customer
from app.domain.language import Language
from app.domain.order import ConfirmedOrder, OrderDraft, OrderItem, OrderState

_CUSTOMER_ID = uuid4()
_DRAFT_ID = uuid4()
_CONV_ID = uuid4()


# ── Static source guards ──────────────────────────────────────────────────────


def test_order_service_confirm_has_no_feedback_enqueue() -> None:
    """confirm() must not import or call enqueue_feedback_request."""
    import app.services.order_service as mod
    source = inspect.getsource(mod)
    assert "enqueue_feedback_request" not in source, (
        "order_service.confirm() must not reference enqueue_feedback_request "
        "— feedback fires at entered_in_pos, not at placement"
    )


def test_entered_in_pos_endpoint_enqueues_feedback() -> None:
    """The entered_in_pos endpoint must call enqueue_feedback_request."""
    import app.api.dispatcher.orders as mod
    source = inspect.getsource(mod)
    assert "enqueue_feedback_request" in source, (
        "orders.entered_in_pos must call enqueue_feedback_request "
        "after marking the order as entered in POS"
    )


# ── Runtime guard ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_runs_without_touching_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    """confirm() completes successfully and never calls enqueue_feedback_request."""
    from app.domain.conversation import Conversation
    from app.services import order_service

    draft = OrderDraft(
        id=_DRAFT_ID,
        customer_id=_CUSTOMER_ID,
        items=[OrderItem(menu_item_id="hummus", quantity=1)],
        fulfillment="pickup",
        language=Language.EN,
    )
    conv = Conversation(id=_CONV_ID, customer_id=_CUSTOMER_ID)

    monkeypatch.setattr("app.services.order_service.validate_ready_to_confirm", AsyncMock(return_value=draft))
    monkeypatch.setattr("app.services.order_service.transcript_repo.get_or_create_conversation", AsyncMock(return_value=conv))
    monkeypatch.setattr("app.services.order_service.transcript_repo.update_conversation", AsyncMock())
    monkeypatch.setattr("app.services.order_service.order_repo.create_confirmed", AsyncMock(side_effect=lambda _s, o: o))
    monkeypatch.setattr("app.services.order_service.draft_store.delete_draft", AsyncMock())
    monkeypatch.setattr("app.services.order_service.menu_repo.get_item", lambda _: None)
    monkeypatch.setattr("app.services.order_service.customer_service.persist_on_confirmation", AsyncMock())
    monkeypatch.setattr("app.services.order_service.check_zone", lambda _: MagicMock(in_zone=True))

    enqueue_calls: list[str] = []

    with patch("app.workers.jobs.enqueue_feedback_request", side_effect=enqueue_calls.append):
        session = AsyncMock()
        session.commit = AsyncMock()
        order = await order_service.confirm(
            session, Customer(id=_CUSTOMER_ID), _DRAFT_ID
        )

    assert order.state == OrderState.AWAITING_DISPATCHER_REVIEW
    assert enqueue_calls == [], (
        "enqueue_feedback_request must not be called during confirm() "
        "— it belongs in the entered_in_pos endpoint"
    )
