"""OrderService — the only path that mutates POS-relevant state.

FR-017, FR-020, FR-022, FR-023, FR-035.
`confirm()` creates the ConfirmedOrder and deletes the Redis draft.
`mark_entered_in_pos()` is the ONLY transition to entered_in_pos.
"""
import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.customer import Customer
from app.domain.errors import OrderValidationCode, OrderValidationError
from app.domain.order import ConfirmedOrder, OrderItem
from app.domain.tools import CheckZoneIn
from app.infra import draft_store
from app.repositories import menu_repo, order_repo, transcript_repo
from app.services.order_draft_service import validate_ready_to_confirm
from app.services.tools.check_zone import check_zone

logger = logging.getLogger(__name__)


def _compute_total(items: list[OrderItem]) -> Decimal:
    total = Decimal("0")
    for item in items:
        menu_item = menu_repo.get_item(item.menu_item_id)
        if menu_item:
            total += menu_item.price_usd * item.quantity
    return total


async def confirm(
    session: AsyncSession,
    customer: Customer,
    draft_id: UUID,
) -> ConfirmedOrder:
    """FR-017, FR-020: Validate draft, create ConfirmedOrder, delete draft."""
    draft = await validate_ready_to_confirm(customer.id)

    if draft.id != draft_id:
        raise OrderValidationError(
            OrderValidationCode.EMPTY_CART, detail="draft_id mismatch"
        )

    flags: list[str] = []
    if draft.fulfillment == "delivery" and draft.address is not None:
        zone_result = check_zone(
            CheckZoneIn(area_label=draft.address.area_label)
        )
        if not zone_result.in_zone and draft.address.area_label is not None:
            flags.append("out_of_zone_warning")

    # Build transcript URL placeholder (transcript_repo stores turns)
    conv = await transcript_repo.get_or_create_conversation(session, customer.id)
    transcript_url = f"/api/transcripts/{conv.id}"

    order = ConfirmedOrder(
        customer_id=customer.id,
        items_snapshot=list(draft.items),
        fulfillment=draft.fulfillment,  # type: ignore[arg-type]
        address_snapshot=draft.address,
        language=draft.language,
        transcript_url=transcript_url,
        estimated_total_usd=_compute_total(draft.items),
        flags=flags,  # type: ignore[arg-type]
    )

    await order_repo.create_confirmed(session, order)

    # Update conversation with order reference
    await transcript_repo.update_conversation(
        session, conv.id, active_draft_id=None
    )
    await session.commit()

    # Delete the Redis draft
    await draft_store.delete_draft(customer.id)

    logger.info(
        "order_confirmed",
        extra={
            "order_id": str(order.id),
            "customer_id": str(customer.id),
            "item_count": len(order.items_snapshot),
        },
    )
    return order


async def mark_entered_in_pos(
    session: AsyncSession,
    order_id: UUID,
    dispatcher_id: str,
    dispatcher_name: str,
) -> ConfirmedOrder:
    """FR-022, FR-023: ONLY path to entered_in_pos state."""
    result = await order_repo.mark_entered_in_pos(
        session, order_id, dispatcher_id, dispatcher_name
    )
    if result is None:
        raise ValueError(f"Order {order_id} not found")
    await session.commit()
    logger.info("order_entered_in_pos", extra={"order_id": str(order_id)})
    return result


async def cancel(
    session: AsyncSession,
    order_id: UUID,
    dispatcher_id: str,
    dispatcher_name: str,
    reason: str,
) -> ConfirmedOrder:
    result = await order_repo.cancel_order(
        session, order_id, dispatcher_id, dispatcher_name, reason
    )
    if result is None:
        raise ValueError(f"Order {order_id} not found")
    await session.commit()
    logger.info("order_cancelled", extra={"order_id": str(order_id)})
    return result
