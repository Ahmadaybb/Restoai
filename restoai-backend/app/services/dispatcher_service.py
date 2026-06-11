"""DispatcherService — order queue, mutation surface, and escalation bridge.

FR-021, FR-022, FR-023, FR-025, FR-026; every mutation appends a
DispatcherAction row carrying dispatcher_id (token hash) and dispatcher_name.
"""
import hashlib
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clients import MessengerClient
from app.domain.conversation import Conversation, Turn
from app.domain.customer import Address, Customer
from app.domain.language import Language
from app.domain.order import ConfirmedOrder, OrderDraft, OrderItem
from app.infra.redaction import redact
from app.repositories import customer_repo, order_repo, transcript_repo

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


# ── Escalation surface (FR-025, FR-026) ──────────────────────────────────────

async def list_escalated(
    session: AsyncSession,
) -> list[tuple[Conversation, Customer]]:
    """Return escalated conversations with their customers."""
    conversations = await transcript_repo.list_escalated(session)
    result: list[tuple[Conversation, Customer]] = []
    for conv in conversations:
        cust = await customer_repo.find_by_id(session, conv.customer_id)
        if cust is not None:
            result.append((conv, cust))
    return result


async def get_escalation_detail(
    session: AsyncSession,
    conversation_id: UUID,
) -> tuple[Conversation, Customer, list[Turn], OrderDraft | None] | None:
    """Return full escalation detail: conversation, customer, transcript, draft."""
    conv = await transcript_repo.get_conversation(session, conversation_id)
    if conv is None:
        return None
    cust = await customer_repo.find_by_id(session, conv.customer_id)
    if cust is None:
        return None
    turns = await transcript_repo.get_turns(session, conversation_id)
    from app.infra import draft_store
    from app.services.order_draft_service import _deserialize

    raw = await draft_store.get_draft(conv.customer_id)
    draft: OrderDraft | None = _deserialize(raw) if raw else None
    return conv, cust, turns, draft


async def send_message(
    session: AsyncSession,
    conversation_id: UUID,
    text: str,
    dispatcher_token: str,
    dispatcher_name: str,
    messenger: MessengerClient,
) -> None:
    """FR-026: Post dispatcher message to the customer's Telegram chat."""
    conv = await transcript_repo.get_conversation(session, conversation_id)
    if conv is None:
        raise ValueError(f"Conversation {conversation_id} not found")
    cust = await customer_repo.find_by_id(session, conv.customer_id)
    if cust is None or cust.telegram_user_id is None:
        raise ValueError("Customer or Telegram id not found")

    attributed = f"👤 [Support]: {text}"
    await messenger.send_message(chat_id=cust.telegram_user_id, text=attributed)

    turn = Turn(
        conversation_id=conversation_id,
        sender="dispatcher",
        text=redact(attributed)[:4000],
        language=Language.EN,
    )
    await transcript_repo.append_turn(session, turn)
    dispatcher_id = _hash_token(dispatcher_token)
    await order_repo.append_dispatcher_action(
        session,
        order_id=None,
        conversation_id=conversation_id,
        dispatcher_id=dispatcher_id,
        dispatcher_name=dispatcher_name,
        action="reply_in_chat",
        details={"text_len": len(text)},
    )
    await session.commit()
    logger.info("dispatcher_message_sent", extra={"conversation_id": str(conversation_id)})
