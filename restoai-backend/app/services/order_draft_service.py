"""OrderDraftService — all OrderDraft mutations against Redis draft_store.

FR-003, FR-004, FR-009, FR-010, FR-018, FR-019; data-model.md §OrderDraft.
Confirms items exist in the menu cache before adding (FR-005).
"""
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.customer import Address
from app.domain.errors import OrderValidationCode, OrderValidationError
from app.domain.language import Language
from app.domain.order import Customization, OrderDraft, OrderItem
from app.infra import draft_store
from app.repositories import menu_repo

logger = logging.getLogger(__name__)


def _deserialize(raw: dict) -> OrderDraft:  # type: ignore[type-arg]
    return OrderDraft.model_validate(raw)


def _serialize(draft: OrderDraft) -> dict:  # type: ignore[type-arg]
    return draft.model_dump(mode="json")


async def get_draft(customer_id: UUID) -> OrderDraft | None:
    raw = await draft_store.get_draft(customer_id)
    if raw is None:
        return None
    return _deserialize(raw)


async def start_draft(customer_id: UUID, language: Language) -> OrderDraft:
    draft = OrderDraft(customer_id=customer_id, language=language)
    await draft_store.put_draft(customer_id, _serialize(draft))
    return draft


async def add_items(
    customer_id: UUID,
    items: list[OrderItem],
) -> OrderDraft:
    """Add or merge items into the active draft. Creates draft if none exists."""
    draft = await get_draft(customer_id)
    if draft is None:
        draft = OrderDraft(customer_id=customer_id)

    for new_item in items:
        # Validate menu_item_id exists (FR-005)
        if menu_repo.get_item(new_item.menu_item_id) is None:
            logger.warning(
                "add_item_unknown_id",
                extra={"menu_item_id": new_item.menu_item_id},
            )
            continue
        # Merge quantity if same item already in cart
        existing = next(
            (i for i in draft.items if i.menu_item_id == new_item.menu_item_id),
            None,
        )
        if existing:
            idx = draft.items.index(existing)
            draft.items[idx] = OrderItem(
                menu_item_id=existing.menu_item_id,
                quantity=existing.quantity + new_item.quantity,
                customizations=existing.customizations + new_item.customizations,
            )
        else:
            draft.items.append(new_item)

    await draft_store.put_draft(customer_id, _serialize(draft))
    return draft


async def attach_customization(
    customer_id: UUID,
    menu_item_id: str,
    customization: Customization,
) -> OrderDraft:
    draft = await get_draft(customer_id)
    if draft is None:
        draft = OrderDraft(customer_id=customer_id)
    for i, item in enumerate(draft.items):
        if item.menu_item_id == menu_item_id:
            draft.items[i] = OrderItem(
                menu_item_id=item.menu_item_id,
                quantity=item.quantity,
                customizations=item.customizations + [customization],
            )
            break
    await draft_store.put_draft(customer_id, _serialize(draft))
    return draft


async def set_fulfillment(
    customer_id: UUID, fulfillment: str
) -> OrderDraft:
    draft = await get_draft(customer_id)
    if draft is None:
        draft = OrderDraft(customer_id=customer_id)
    draft = draft.model_copy(update={"fulfillment": fulfillment})
    await draft_store.put_draft(customer_id, _serialize(draft))
    return draft


async def attach_address(
    customer_id: UUID,
    address: Address,
    *,
    session: AsyncSession | None = None,
) -> OrderDraft:
    """Attach address to draft. If session is provided, also persists to Postgres (T088)."""
    if session is not None:
        from app.repositories import customer_repo
        if address.customer_id is None:
            address = address.model_copy(update={"customer_id": customer_id})
        await customer_repo.save_address(session, address)
        await session.flush()
    draft = await get_draft(customer_id)
    if draft is None:
        draft = OrderDraft(customer_id=customer_id)
    draft = draft.model_copy(update={"address": address})
    await draft_store.put_draft(customer_id, _serialize(draft))
    return draft


async def attach_location(
    customer_id: UUID,
    lat: float,
    lon: float,
    *,
    session: AsyncSession | None = None,
) -> OrderDraft:
    address = Address(
        customer_id=customer_id,
        kind="location",
        lat=lat,
        lon=lon,
        in_zone=True,
    )
    return await attach_address(customer_id, address, session=session)


async def select_saved_address(
    customer_id: UUID, address: Address
) -> OrderDraft:
    return await attach_address(customer_id, address)


async def reopen_for_edit(customer_id: UUID, draft_id: UUID) -> OrderDraft:
    """FR-018: Clear items so the customer re-states their order; preserve fulfillment/address."""
    draft = await get_draft(customer_id)
    if draft is None or draft.id != draft_id:
        draft = OrderDraft(customer_id=customer_id)
    draft = draft.model_copy(update={"items": []})
    await draft_store.put_draft(customer_id, _serialize(draft))
    return draft


async def validate_ready_to_confirm(
    customer_id: UUID,
) -> OrderDraft:
    """Validate draft is ready and raise OrderValidationError if not. FR-019."""
    draft = await get_draft(customer_id)
    if draft is None or len(draft.items) == 0:
        raise OrderValidationError(OrderValidationCode.EMPTY_CART)
    if draft.fulfillment is None:
        raise OrderValidationError(OrderValidationCode.MISSING_FULFILLMENT)
    if draft.fulfillment == "delivery" and draft.address is None:
        raise OrderValidationError(OrderValidationCode.MISSING_ADDRESS)
    for item in draft.items:
        menu_item = menu_repo.get_item(item.menu_item_id)
        if menu_item is None or not menu_item.available:
            raise OrderValidationError(
                OrderValidationCode.ITEM_UNAVAILABLE,
                detail=item.menu_item_id,
            )
    return draft
