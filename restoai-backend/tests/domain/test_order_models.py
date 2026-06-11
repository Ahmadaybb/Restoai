"""T066: Domain model Pydantic validation tests for order models."""
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.language import Language
from app.domain.order import (
    ConfirmedOrder,
    Customization,
    OrderDraft,
    OrderItem,
    OrderState,
)

# ─── Customization ────────────────────────────────────────────────────────────

def test_customization_valid_kinds() -> None:
    for kind in ("add", "remove", "cook_pref", "extra_side", "other"):
        c = Customization(kind=kind, text="test")  # type: ignore[arg-type]
        assert c.kind == kind


def test_customization_text_required() -> None:
    with pytest.raises(Exception):
        Customization(kind="add", text="")


def test_customization_invalid_kind_rejected() -> None:
    with pytest.raises(Exception):
        Customization(kind="unknown_kind", text="test")  # type: ignore[arg-type]


# ─── OrderItem ────────────────────────────────────────────────────────────────

def test_order_item_quantity_ge_1() -> None:
    with pytest.raises(Exception):
        OrderItem(menu_item_id="hummus", quantity=0)


def test_order_item_menu_item_id_required() -> None:
    with pytest.raises(Exception):
        OrderItem(menu_item_id="", quantity=1)


def test_order_item_default_no_customizations() -> None:
    item = OrderItem(menu_item_id="hummus", quantity=1)
    assert item.customizations == []


def test_order_item_with_customizations() -> None:
    item = OrderItem(
        menu_item_id="hummus",
        quantity=1,
        customizations=[Customization(kind="remove", text="no garlic")],
    )
    assert len(item.customizations) == 1
    assert item.customizations[0].text == "no garlic"


# ─── OrderDraft ───────────────────────────────────────────────────────────────

def test_order_draft_default_state() -> None:
    draft = OrderDraft(customer_id=uuid4())
    assert draft.items == []
    assert draft.fulfillment is None
    assert draft.address is None
    assert draft.language == Language.EN


def test_order_draft_expires_at_set_automatically() -> None:
    draft = OrderDraft(customer_id=uuid4())
    assert draft.expires_at is not None
    delta = draft.expires_at - draft.created_at
    # TTL is 2 hours
    assert delta.total_seconds() == pytest.approx(7200, abs=1)


def test_order_draft_language_arabic() -> None:
    draft = OrderDraft(customer_id=uuid4(), language=Language.AR_LB)
    assert draft.language == Language.AR_LB


# ─── ConfirmedOrder ───────────────────────────────────────────────────────────

def test_confirmed_order_default_state() -> None:
    order = ConfirmedOrder(
        customer_id=uuid4(),
        items_snapshot=[],
        fulfillment="pickup",
        language=Language.EN,
        transcript_url="/t/1",
        estimated_total_usd=Decimal("0"),
    )
    assert order.state == OrderState.AWAITING_DISPATCHER_REVIEW


def test_confirmed_order_total_ge_zero() -> None:
    with pytest.raises(Exception):
        ConfirmedOrder(
            customer_id=uuid4(),
            items_snapshot=[],
            fulfillment="pickup",
            language=Language.EN,
            transcript_url="/t/1",
            estimated_total_usd=Decimal("-1"),
        )


def test_confirmed_order_fulfillment_must_be_valid() -> None:
    with pytest.raises(Exception):
        ConfirmedOrder(
            customer_id=uuid4(),
            items_snapshot=[],
            fulfillment="flying",  # type: ignore[arg-type]
            language=Language.EN,
            transcript_url="/t/1",
            estimated_total_usd=Decimal("0"),
        )


def test_confirmed_order_flags_out_of_zone() -> None:
    order = ConfirmedOrder(
        customer_id=uuid4(),
        items_snapshot=[],
        fulfillment="delivery",
        language=Language.EN,
        transcript_url="/t/1",
        estimated_total_usd=Decimal("10"),
        flags=["out_of_zone_warning"],
    )
    assert "out_of_zone_warning" in order.flags


def test_order_state_str_values() -> None:
    assert str(OrderState.AWAITING_DISPATCHER_REVIEW) == "awaiting_dispatcher_review"
    assert str(OrderState.ENTERED_IN_POS) == "entered_in_pos"
    assert str(OrderState.CANCELLED) == "cancelled"
