"""OrderRepository — Postgres writes/reads for ConfirmedOrder only.

Drafts are Redis-only (see app/infra/draft_store.py). The first Postgres
artifact in the order lifecycle is the ConfirmedOrder.
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ConfirmedOrder as OrderORM
from app.db.models import Customer as CustomerORM
from app.db.models import DispatcherAction as ActionORM
from app.domain.customer import Address, Customer
from app.domain.order import ConfirmedOrder, Customization, OrderItem, OrderState


def _items_to_json(items: list[OrderItem]) -> list[dict[str, Any]]:
    return [
        {
            "menu_item_id": it.menu_item_id,
            "quantity": it.quantity,
            "customizations": [
                {"kind": c.kind, "text": c.text} for c in it.customizations
            ],
        }
        for it in items
    ]


def _address_to_json(addr: Address | None) -> dict[str, Any] | None:
    if addr is None:
        return None
    return {
        "id": str(addr.id),
        "kind": addr.kind,
        "text_value": addr.text_value,
        "lat": addr.lat,
        "lon": addr.lon,
        "area_label": addr.area_label,
        "in_zone": addr.in_zone,
    }


def _orm_to_domain(row: OrderORM) -> ConfirmedOrder:
    items_data: list[dict[str, Any]] = row.items_snapshot or []
    items = [
        OrderItem(
            menu_item_id=it["menu_item_id"],
            quantity=it["quantity"],
            customizations=[
                Customization(kind=c["kind"], text=c["text"])
                for c in it.get("customizations", [])
            ],
        )
        for it in items_data
    ]
    addr_data: dict[str, Any] | None = row.address_snapshot
    address: Address | None = None
    if addr_data:
        address = Address(
            id=uuid.UUID(addr_data["id"]),
            kind=addr_data["kind"],
            text_value=addr_data.get("text_value"),
            lat=addr_data.get("lat"),
            lon=addr_data.get("lon"),
            area_label=addr_data.get("area_label"),
            in_zone=addr_data.get("in_zone", True),
        )
    return ConfirmedOrder(
        id=row.id,
        customer_id=row.customer_id,
        items_snapshot=items,
        fulfillment=row.fulfillment,  # type: ignore[arg-type]
        address_snapshot=address,
        language=row.language,  # type: ignore[arg-type]
        transcript_url=row.transcript_url,
        estimated_total_usd=Decimal(str(row.estimated_total_usd)),
        flags=list(row.flags or []),
        state=OrderState(row.state),
        created_at=row.created_at,
        dispatcher_id=row.dispatcher_id,
        entered_in_pos_at=row.entered_in_pos_at,
    )


async def create_confirmed(
    session: AsyncSession,
    order: ConfirmedOrder,
) -> ConfirmedOrder:
    row = OrderORM(
        id=order.id,
        customer_id=order.customer_id,
        items_snapshot=_items_to_json(order.items_snapshot),
        fulfillment=order.fulfillment,
        address_snapshot=_address_to_json(order.address_snapshot),
        language=order.language,
        transcript_url=order.transcript_url,
        estimated_total_usd=order.estimated_total_usd,
        flags=list(order.flags),
        state=order.state.value,
    )
    session.add(row)
    await session.flush()
    return order


async def get(
    session: AsyncSession, order_id: uuid.UUID
) -> tuple[ConfirmedOrder, Customer] | None:
    result = await session.execute(
        select(OrderORM)
        .where(OrderORM.id == order_id)
        .options(
            selectinload(OrderORM.customer).selectinload(CustomerORM.addresses),
            selectinload(OrderORM.dispatcher_actions),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    from app.repositories.customer_repo import _orm_to_domain as customer_orm_to_domain

    customer = customer_orm_to_domain(row.customer)
    return _orm_to_domain(row), customer


async def list_awaiting_review(
    session: AsyncSession,
    flag: str | None = None,
    limit: int = 50,
) -> list[tuple[ConfirmedOrder, Customer]]:
    q = (
        select(OrderORM)
        .where(OrderORM.state == "awaiting_dispatcher_review")
        .options(
            selectinload(OrderORM.customer).selectinload(CustomerORM.addresses)
        )
        .order_by(OrderORM.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(q)
    rows = result.scalars().all()
    from app.repositories.customer_repo import _orm_to_domain as customer_orm_to_domain

    orm_pairs = [(row, customer_orm_to_domain(row.customer)) for row in rows]
    if flag:
        converted: list[tuple[ConfirmedOrder, Customer]] = [
            (_orm_to_domain(row), cu) for row, cu in orm_pairs
        ]
        return [(o, c) for o, c in converted if flag in o.flags]
    return [(_orm_to_domain(row), c) for row, c in orm_pairs]


async def apply_edit(
    session: AsyncSession,
    order_id: uuid.UUID,
    items: list[OrderItem] | None = None,
    fulfillment: str | None = None,
    address: Address | None = None,
) -> ConfirmedOrder | None:
    result = await session.execute(
        select(OrderORM).where(OrderORM.id == order_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    if items is not None:
        row.items_snapshot = _items_to_json(items)
    if fulfillment is not None:
        row.fulfillment = fulfillment
    if address is not None:
        row.address_snapshot = _address_to_json(address)
    await session.flush()
    return _orm_to_domain(row)


async def mark_entered_in_pos(
    session: AsyncSession,
    order_id: uuid.UUID,
    dispatcher_id: str,
    dispatcher_name: str,
) -> ConfirmedOrder | None:
    result = await session.execute(
        select(OrderORM).where(OrderORM.id == order_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    if row.state == "entered_in_pos":
        return _orm_to_domain(row)
    row.state = "entered_in_pos"
    row.dispatcher_id = dispatcher_id
    row.entered_in_pos_at = datetime.now(tz=UTC)
    action = ActionORM(
        order_id=order_id,
        dispatcher_id=dispatcher_id,
        dispatcher_name=dispatcher_name,
        action="mark_entered_in_pos",
        details={},
    )
    session.add(action)
    await session.flush()
    return _orm_to_domain(row)


async def cancel_order(
    session: AsyncSession,
    order_id: uuid.UUID,
    dispatcher_id: str,
    dispatcher_name: str,
    reason: str,
) -> ConfirmedOrder | None:
    result = await session.execute(
        select(OrderORM).where(OrderORM.id == order_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.state = "cancelled"
    row.dispatcher_id = dispatcher_id
    action = ActionORM(
        order_id=order_id,
        dispatcher_id=dispatcher_id,
        dispatcher_name=dispatcher_name,
        action="cancel",
        details={"reason": reason},
    )
    session.add(action)
    await session.flush()
    return _orm_to_domain(row)


async def append_dispatcher_action(
    session: AsyncSession,
    order_id: uuid.UUID | None,
    dispatcher_id: str,
    dispatcher_name: str,
    action: str,
    details: dict[str, Any] | None = None,
    conversation_id: uuid.UUID | None = None,
) -> None:
    row = ActionORM(
        order_id=order_id,
        conversation_id=conversation_id,
        dispatcher_id=dispatcher_id,
        dispatcher_name=dispatcher_name,
        action=action,
        details=details or {},
    )
    session.add(row)
    await session.flush()
