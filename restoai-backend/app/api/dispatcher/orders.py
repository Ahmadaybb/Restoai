"""Dispatcher REST surface for orders.

FR-020, FR-021, FR-022, FR-023; contracts/dispatcher_api.openapi.yaml.
"""
import logging
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dispatcher.auth import require_auth, validate_dispatcher_name
from app.db.engine import get_session
from app.domain.customer import Address, Customer
from app.domain.order import ConfirmedOrder, OrderItem
from app.repositories import menu_repo
from app.services import dispatcher_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dispatcher", tags=["dispatcher"])


# ── Response schemas ──────────────────────────────────────────────────────────

class CustomizationOut(BaseModel):
    kind: str
    text: str


class OrderItemOut(BaseModel):
    menu_item_id: str
    name: str
    quantity: int
    price_usd: float
    customizations: list[CustomizationOut]


class AddressOut(BaseModel):
    kind: str
    text_value: str | None = None
    lat: float | None = None
    lon: float | None = None
    area_label: str | None = None
    in_zone: bool


class OrderSummaryOut(BaseModel):
    id: UUID
    customer_name: str
    customer_phone: str
    fulfillment: str
    language: str
    estimated_total_usd: float
    flags: list[str]
    state: str
    created_at: datetime


class DispatcherActionOut(BaseModel):
    action: str
    dispatcher_id: str
    dispatcher_name: str
    details: dict[str, Any]
    created_at: datetime


class OrderDetailOut(OrderSummaryOut):
    address: AddressOut | None = None
    items: list[OrderItemOut]
    transcript_url: str
    entered_in_pos_at: datetime | None = None
    dispatcher_actions: list[DispatcherActionOut] = []


# ── Request schemas ───────────────────────────────────────────────────────────

class EnteredInPosRequest(BaseModel):
    dispatcher_name: str


class CancelRequest(BaseModel):
    dispatcher_name: str
    reason: str


class EditItemIn(BaseModel):
    menu_item_id: str
    name: str = ""
    quantity: int = 1
    price_usd: float = 0.0
    customizations: list[CustomizationOut] = []


class AddressIn(BaseModel):
    kind: str
    text_value: str | None = None
    lat: float | None = None
    lon: float | None = None
    area_label: str | None = None
    in_zone: bool = True


class OrderEditRequest(BaseModel):
    dispatcher_name: str
    items: list[EditItemIn] | None = None
    fulfillment: str | None = None
    address: AddressIn | None = None
    note: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _item_out(item: OrderItem) -> OrderItemOut:
    menu_item = menu_repo.get_item(item.menu_item_id)
    return OrderItemOut(
        menu_item_id=item.menu_item_id,
        name=menu_item.name_en if menu_item else item.menu_item_id,
        quantity=item.quantity,
        price_usd=float(menu_item.price_usd) if menu_item else 0.0,
        customizations=[
            CustomizationOut(kind=c.kind, text=c.text) for c in item.customizations
        ],
    )


def _addr_out(addr: Address | None) -> AddressOut | None:
    if addr is None:
        return None
    return AddressOut(
        kind=addr.kind,
        text_value=addr.text_value,
        lat=addr.lat,
        lon=addr.lon,
        area_label=addr.area_label,
        in_zone=addr.in_zone,
    )


def _summary_out(order: ConfirmedOrder, customer: Customer) -> OrderSummaryOut:
    return OrderSummaryOut(
        id=order.id,
        customer_name=customer.display_name or "Unknown",
        customer_phone=customer.phone_e164 or "",
        fulfillment=order.fulfillment,
        language=order.language.value if hasattr(order.language, "value") else str(order.language),
        estimated_total_usd=float(order.estimated_total_usd),
        flags=list(order.flags),
        state=order.state.value if hasattr(order.state, "value") else str(order.state),
        created_at=order.created_at,
    )


def _detail_out(order: ConfirmedOrder, customer: Customer) -> OrderDetailOut:
    summary = _summary_out(order, customer)
    return OrderDetailOut(
        **summary.model_dump(),
        address=_addr_out(order.address_snapshot),
        items=[_item_out(i) for i in order.items_snapshot],
        transcript_url=order.transcript_url,
        entered_in_pos_at=order.entered_in_pos_at,
    )


_NOT_FOUND = HTTPException(
    status_code=404, detail={"code": "NOT_FOUND", "message": "Order not found"}
)

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/orders", response_model=dict)
async def list_orders(
    flag: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    token: str = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    pairs = await dispatcher_service.list_orders(session, flag=flag, limit=limit)
    return {"orders": [_summary_out(o, c).model_dump() for o, c in pairs]}


@router.get("/orders/{order_id}", response_model=OrderDetailOut)
async def get_order(
    order_id: UUID,
    token: str = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> OrderDetailOut:
    result = await dispatcher_service.get_order(session, order_id)
    if result is None:
        raise _NOT_FOUND
    order, customer = result
    return _detail_out(order, customer)


@router.patch("/orders/{order_id}", response_model=OrderDetailOut)
async def edit_order(
    order_id: UUID,
    body: OrderEditRequest,
    token: str = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> OrderDetailOut:
    dispatcher_name = validate_dispatcher_name(body.dispatcher_name)

    items: list[OrderItem] | None = None
    if body.items is not None:
        from app.domain.order import Customization
        items = [
            OrderItem(
                menu_item_id=i.menu_item_id,
                quantity=i.quantity,
                customizations=[Customization(kind=c.kind, text=c.text) for c in i.customizations],  # type: ignore[arg-type]
            )
            for i in body.items
        ]

    address: Address | None = None
    if body.address is not None:
        address = Address(
            kind=body.address.kind,  # type: ignore[arg-type]
            text_value=body.address.text_value,
            lat=body.address.lat,
            lon=body.address.lon,
            area_label=body.address.area_label,
            in_zone=body.address.in_zone,
        )

    result = await dispatcher_service.edit_order(
        session,
        order_id=order_id,
        dispatcher_token=token,
        dispatcher_name=dispatcher_name,
        items=items,
        fulfillment=body.fulfillment,
        address=address,
        note=body.note,
    )
    if result is None:
        raise _NOT_FOUND
    pair = await dispatcher_service.get_order(session, order_id)
    if pair is None:
        raise _NOT_FOUND
    return _detail_out(*pair)


@router.post("/orders/{order_id}/entered-in-pos", response_model=OrderDetailOut)
async def entered_in_pos(
    order_id: UUID,
    body: EnteredInPosRequest,
    token: str = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> OrderDetailOut:
    dispatcher_name = validate_dispatcher_name(body.dispatcher_name)
    result = await dispatcher_service.mark_entered_in_pos(
        session, order_id, token, dispatcher_name
    )
    if result is None:
        raise _NOT_FOUND
    pair = await dispatcher_service.get_order(session, order_id)
    if pair is None:
        raise _NOT_FOUND
    return _detail_out(*pair)


@router.post("/orders/{order_id}/cancel", response_model=OrderDetailOut)
async def cancel_order(
    order_id: UUID,
    body: CancelRequest,
    token: str = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> OrderDetailOut:
    dispatcher_name = validate_dispatcher_name(body.dispatcher_name)
    result = await dispatcher_service.cancel_order(
        session, order_id, token, dispatcher_name, body.reason
    )
    if result is None:
        raise _NOT_FOUND
    pair = await dispatcher_service.get_order(session, order_id)
    if pair is None:
        raise _NOT_FOUND
    return _detail_out(*pair)
