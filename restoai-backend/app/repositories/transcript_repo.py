"""TranscriptRepository — append-only conversation + turn log.

One Conversation row per customer chat session; one Turn row per message.
The transcript_url served in the dispatcher API is constructed from the
conversation id.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation as ConvORM
from app.db.models import Turn as TurnORM
from app.domain.conversation import Conversation, Turn
from app.domain.language import Intent, Language


def _conv_to_domain(row: ConvORM) -> Conversation:
    return Conversation(
        id=row.id,
        customer_id=row.customer_id,
        started_at=row.started_at,
        last_activity_at=row.last_activity_at,
        awaiting_human=row.awaiting_human,
        assigned_dispatcher_id=row.assigned_dispatcher_id,
        active_draft_id=row.active_draft_id,
    )


def _turn_to_domain(row: TurnORM) -> Turn:
    return Turn(
        id=row.id,
        conversation_id=row.conversation_id,
        sender=row.sender,  # type: ignore[arg-type]
        text=row.text,
        language=Language(row.language),
        intent=Intent(row.intent) if row.intent else None,
        created_at=row.created_at,
    )


async def get_or_create_conversation(
    session: AsyncSession, customer_id: uuid.UUID
) -> Conversation:
    result = await session.execute(
        select(ConvORM)
        .where(ConvORM.customer_id == customer_id)
        .order_by(ConvORM.last_activity_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = ConvORM(customer_id=customer_id)
        session.add(row)
        await session.flush()
    return _conv_to_domain(row)


async def get_conversation(
    session: AsyncSession, conversation_id: uuid.UUID
) -> Conversation | None:
    result = await session.execute(
        select(ConvORM).where(ConvORM.id == conversation_id)
    )
    row = result.scalar_one_or_none()
    return _conv_to_domain(row) if row else None


async def update_conversation(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    **kwargs: object,
) -> None:
    result = await session.execute(
        select(ConvORM).where(ConvORM.id == conversation_id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        for k, v in kwargs.items():
            setattr(row, k, v)
        row.last_activity_at = datetime.now(tz=UTC)
        await session.flush()


async def append_turn(session: AsyncSession, turn: Turn) -> Turn:
    row = TurnORM(
        id=turn.id,
        conversation_id=turn.conversation_id,
        sender=turn.sender,
        text=turn.text,
        language=turn.language.value,
        intent=turn.intent.value if turn.intent else None,
    )
    session.add(row)
    await session.flush()
    return turn


async def list_escalated(
    session: AsyncSession,
) -> list[Conversation]:
    """Return all conversations with awaiting_human=True, newest first."""
    result = await session.execute(
        select(ConvORM)
        .where(ConvORM.awaiting_human.is_(True))
        .order_by(ConvORM.last_activity_at.desc())
    )
    return [_conv_to_domain(row) for row in result.scalars().all()]


async def get_last_turn(
    session: AsyncSession, conversation_id: uuid.UUID
) -> Turn | None:
    result = await session.execute(
        select(TurnORM)
        .where(TurnORM.conversation_id == conversation_id)
        .order_by(TurnORM.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return _turn_to_domain(row) if row else None


async def get_turns(
    session: AsyncSession, conversation_id: uuid.UUID
) -> list[Turn]:
    result = await session.execute(
        select(TurnORM)
        .where(TurnORM.conversation_id == conversation_id)
        .order_by(TurnORM.created_at)
    )
    return [_turn_to_domain(r) for r in result.scalars().all()]
