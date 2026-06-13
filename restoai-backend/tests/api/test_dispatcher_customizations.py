"""T084: GET /api/dispatcher/orders/{id} surfaces customizations per item.

Every customization attached to an order item must appear in the API response
under its parent item. FR-020; contracts/dispatcher_api.openapi.yaml §OrderItem.
"""
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.customer import Customer
from app.domain.language import Language
from app.domain.menu import MenuItem
from app.domain.order import (
    ConfirmedOrder,
    Customization,
    OrderItem,
    OrderState,
)

# ── Shared data ────────────────────────────────────────────────────────────────

_ORDER_ID = uuid4()
_CUSTOMER_ID = uuid4()

_HUMMUS = MenuItem(
    id="cold_mezza_hummus",
    category="COLD MEZZA",
    name_en="Hummus",
    name_ar="حمص",
    price_usd=Decimal("7.00"),
)
_FATTOUSH = MenuItem(
    id="salad_fattoush",
    category="SALADS",
    name_en="Fattoush",
    name_ar="فتوش",
    price_usd=Decimal("6.00"),
)


def _order() -> ConfirmedOrder:
    return ConfirmedOrder(
        id=_ORDER_ID,
        customer_id=_CUSTOMER_ID,
        items_snapshot=[
            OrderItem(
                menu_item_id="cold_mezza_hummus",
                quantity=2,
                customizations=[
                    Customization(kind="remove", text="no onions"),
                    Customization(kind="add", text="extra lemon"),
                ],
            ),
            OrderItem(
                menu_item_id="salad_fattoush",
                quantity=1,
                customizations=[
                    Customization(kind="extra_side", text="pita on the side"),
                ],
            ),
        ],
        fulfillment="pickup",
        language=Language.EN,
        transcript_url="http://localhost/transcript/1",
        estimated_total_usd=Decimal("20.00"),
        state=OrderState.AWAITING_DISPATCHER_REVIEW,
        created_at=datetime.now(tz=UTC),
    )


def _customer() -> Customer:
    return Customer(
        id=_CUSTOMER_ID,
        display_name="Test User",
        phone_e164="+96170000000",
    )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_item_mock(item_id: str) -> MenuItem | None:
    return {"cold_mezza_hummus": _HUMMUS, "salad_fattoush": _FATTOUSH}.get(item_id)


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_order_includes_customizations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/dispatcher/orders/{id} must return customizations nested under each item."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.api.dispatcher.auth import require_auth
    from app.api.dispatcher.orders import router
    from app.db.engine import get_session

    # Minimal FastAPI app — no lifespan, no DB, no Redis
    test_app = FastAPI()
    test_app.include_router(router)

    fake_session = AsyncMock(spec=AsyncSession)

    async def _override_session() -> Any:
        yield fake_session

    async def _override_auth() -> str:
        return "test-token"

    test_app.dependency_overrides[get_session] = _override_session
    test_app.dependency_overrides[require_auth] = _override_auth

    monkeypatch.setattr(
        "app.services.dispatcher_service.get_order",
        AsyncMock(return_value=(_order(), _customer())),
    )
    monkeypatch.setattr("app.repositories.menu_repo.get_item", _get_item_mock)

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/dispatcher/orders/{_ORDER_ID}",
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()

    items = data["items"]
    assert len(items) == 2

    hummus = next(i for i in items if i["menu_item_id"] == "cold_mezza_hummus")
    fattoush = next(i for i in items if i["menu_item_id"] == "salad_fattoush")

    # Hummus: two customizations
    assert len(hummus["customizations"]) == 2
    hummus_texts = {c["text"] for c in hummus["customizations"]}
    assert "no onions" in hummus_texts
    assert "extra lemon" in hummus_texts

    # Fattoush: one customization
    assert len(fattoush["customizations"]) == 1
    assert fattoush["customizations"][0]["text"] == "pita on the side"
    assert fattoush["customizations"][0]["kind"] == "extra_side"


@pytest.mark.asyncio
async def test_get_order_no_customizations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Items with no customizations return an empty list, not null."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.api.dispatcher.auth import require_auth
    from app.api.dispatcher.orders import router
    from app.db.engine import get_session

    plain_order = ConfirmedOrder(
        id=_ORDER_ID,
        customer_id=_CUSTOMER_ID,
        items_snapshot=[
            OrderItem(menu_item_id="cold_mezza_hummus", quantity=1, customizations=[]),
        ],
        fulfillment="pickup",
        language=Language.EN,
        transcript_url="",
        estimated_total_usd=Decimal("7.00"),
        state=OrderState.AWAITING_DISPATCHER_REVIEW,
        created_at=datetime.now(tz=UTC),
    )

    test_app = FastAPI()
    test_app.include_router(router)

    fake_session = AsyncMock(spec=AsyncSession)

    async def _override_session() -> Any:
        yield fake_session

    async def _override_auth() -> str:
        return "test-token"

    test_app.dependency_overrides[get_session] = _override_session
    test_app.dependency_overrides[require_auth] = _override_auth

    monkeypatch.setattr(
        "app.services.dispatcher_service.get_order",
        AsyncMock(return_value=(plain_order, _customer())),
    )
    monkeypatch.setattr("app.repositories.menu_repo.get_item", _get_item_mock)

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/dispatcher/orders/{_ORDER_ID}",
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["customizations"] == []
