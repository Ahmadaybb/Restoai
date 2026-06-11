"""DispatcherService — order queue and mutation surface for the dispatcher.

FR-021, FR-022, FR-023; every mutation appends a DispatcherAction row
carrying dispatcher_id (token hash) and dispatcher_name.
"""
import hashlib
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.customer import Address, Customer
from app.domain.order import ConfirmedOrder, OrderItem
from app.repositories import order_repo

logger = logging.getLogger(__name__)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


async def list_orders(
    session: AsyncSession,
    flag: str | None = None,
    limit: int = 50,
) -> list[tuple[ConfirmedOrder, Customer]]:
    return await order_repo.list_awaiting_review(session, flag=flag, limit=limit)


async def get_order(
    session: AsyncSession, order_id: UUID
) -> tuple[ConfirmedOrder, Customer] | None:
    return await order_repo.get(session, order_id)


async def edit_order(
    session: AsyncSession,
    order_id: UUID,
    dispatcher_token: str,
    dispatcher_name: str,
    items: list[OrderItem] | None = None,
    fulfillment: str | None = None,
    address: Address | None = None,
    note: str | None = None,
) -> ConfirmedOrder | None:
    dispatcher_id = _hash_token(dispatcher_token)
    result = await order_repo.apply_edit(
        session, order_id, items=items, fulfillment=fulfillment, address=address
    )
    if result is None:
        return None
    details: dict[str, Any] = {}
    if note:
        details["note"] = note
    await order_repo.append_dispatcher_action(
        session,
        order_id=order_id,
        dispatcher_id=dispatcher_id,
        dispatcher_name=dispatcher_name,
        action="edit",
        details=details,
    )
    await session.commit()
    logger.info("order_edited", extra={"order_id": str(order_id)})
    return result


async def mark_entered_in_pos(
    session: AsyncSession,
    order_id: UUID,
    dispatcher_token: str,
    dispatcher_name: str,
) -> ConfirmedOrder | None:
    dispatcher_id = _hash_token(dispatcher_token)
    from app.services.order_service import mark_entered_in_pos as svc_mark

    return await svc_mark(session, order_id, dispatcher_id, dispatcher_name)


async def cancel_order(
    session: AsyncSession,
    order_id: UUID,
    dispatcher_token: str,
    dispatcher_name: str,
    reason: str,
) -> ConfirmedOrder | None:
    dispatcher_id = _hash_token(dispatcher_token)
    from app.services.order_service import cancel as svc_cancel

    return await svc_cancel(
        session, order_id, dispatcher_id, dispatcher_name, reason
    )
