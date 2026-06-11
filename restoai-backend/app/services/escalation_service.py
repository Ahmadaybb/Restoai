"""EscalationService — 3-strike human-escalation logic.

register_failure: increments per-field failure counter; on the 3rd
  consecutive failure sets Conversation.awaiting_human = True, resets
  that counter (so a handoff close doesn't immediately re-escalate),
  and fires a best-effort dispatcher_notify RQ job.

take_over: sets Conversation.assigned_dispatcher_id and appends a
  take_over_chat DispatcherAction.

close_handoff: clears awaiting_human and resets all failure counters,
  appends close_handoff DispatcherAction.

FR-024, FR-025, FR-026.
"""
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.infra import draft_store
from app.repositories import order_repo, transcript_repo

logger = logging.getLogger(__name__)

ESCALATION_THRESHOLD = 3
_ALL_FIELDS = ("order_parse", "dish_match", "address_extract")


async def register_failure(
    session: AsyncSession,
    customer_id: UUID,
    field: str,
) -> bool:
    """Increment field counter; return True when the 3rd failure fires escalation."""
    count = await draft_store.incr_failcount(customer_id, field)
    if count >= ESCALATION_THRESHOLD:
        conv = await transcript_repo.get_or_create_conversation(session, customer_id)
        await transcript_repo.update_conversation(
            session, conv.id, awaiting_human=True
        )
        await session.commit()
        await draft_store.reset_failcount(customer_id, field)
        logger.info(
            "escalation_triggered",
            extra={"customer_id": str(customer_id), "field": field},
        )
        _try_enqueue_notify(conv.id)
        return True
    return False


async def take_over(
    session: AsyncSession,
    conversation_id: UUID,
    dispatcher_id: str,
    dispatcher_name: str,
) -> None:
    """Assign dispatcher to conversation; idempotent if already assigned."""
    await transcript_repo.update_conversation(
        session, conversation_id, assigned_dispatcher_id=dispatcher_id
    )
    await order_repo.append_dispatcher_action(
        session,
        order_id=None,
        conversation_id=conversation_id,
        dispatcher_id=dispatcher_id,
        dispatcher_name=dispatcher_name,
        action="take_over_chat",
    )
    await session.commit()
    logger.info("take_over", extra={"conversation_id": str(conversation_id)})


async def close_handoff(
    session: AsyncSession,
    conversation_id: UUID,
    customer_id: UUID,
    dispatcher_id: str,
    dispatcher_name: str,
) -> None:
    """Return conversation to the bot and reset all failure counters."""
    await transcript_repo.update_conversation(
        session,
        conversation_id,
        awaiting_human=False,
        assigned_dispatcher_id=None,
    )
    for field in _ALL_FIELDS:
        await draft_store.reset_failcount(customer_id, field)
    await order_repo.append_dispatcher_action(
        session,
        order_id=None,
        conversation_id=conversation_id,
        dispatcher_id=dispatcher_id,
        dispatcher_name=dispatcher_name,
        action="close_handoff",
    )
    await session.commit()
    logger.info("close_handoff", extra={"conversation_id": str(conversation_id)})


def _try_enqueue_notify(conversation_id: UUID) -> None:
    """Best-effort RQ enqueue — silently skipped when worker is not running."""
    try:
        import rq

        from app.infra.redis_client import get_redis
        queue = rq.Queue(connection=get_redis())  # type: ignore[arg-type]
        queue.enqueue("app.workers.jobs.dispatcher_notify", str(conversation_id))
    except Exception:  # noqa: BLE001
        logger.debug("dispatcher_notify_enqueue_skipped")
