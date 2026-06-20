"""FeedbackRepository — Postgres reads/writes for OrderFeedback."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ConfirmedOrder as OrderORM
from app.db.models import Customer as CustomerORM
from app.db.models import OrderFeedbackORM
from app.domain.feedback import FeedbackStatus, OrderFeedback, Sentiment


def _orm_to_domain(row: OrderFeedbackORM) -> OrderFeedback:
    return OrderFeedback(
        id=row.id,
        order_id=row.order_id,
        customer_id=row.customer_id,
        conversation_id=row.conversation_id,
        star_rating=row.star_rating,
        comment=row.comment,
        sentiment=Sentiment(row.sentiment) if row.sentiment else None,
        status=FeedbackStatus(row.status),
        feedback_requested_at=row.feedback_requested_at,
        reminder_sent_at=row.reminder_sent_at,
        responded_at=row.responded_at,
        created_at=row.created_at,
    )


@dataclass
class FeedbackRow:
    feedback: OrderFeedback
    items_snapshot: list[Any]
    customer_name: str | None
    customer_phone: str | None


async def create(
    session: AsyncSession,
    order_id: uuid.UUID,
    customer_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
) -> OrderFeedback:
    row = OrderFeedbackORM(
        id=uuid.uuid4(),
        order_id=order_id,
        customer_id=customer_id,
        conversation_id=conversation_id,
        status=FeedbackStatus.PENDING.value,
        feedback_requested_at=datetime.now(tz=UTC),
    )
    session.add(row)
    await session.flush()
    return _orm_to_domain(row)


async def get_by_id(
    session: AsyncSession, feedback_id: uuid.UUID
) -> OrderFeedback | None:
    result = await session.execute(
        select(OrderFeedbackORM).where(OrderFeedbackORM.id == feedback_id)
    )
    row = result.scalar_one_or_none()
    return _orm_to_domain(row) if row else None


async def get_by_order_id(
    session: AsyncSession, order_id: uuid.UUID
) -> OrderFeedback | None:
    result = await session.execute(
        select(OrderFeedbackORM).where(OrderFeedbackORM.order_id == order_id)
    )
    row = result.scalar_one_or_none()
    return _orm_to_domain(row) if row else None


async def get_by_status(
    session: AsyncSession, status: FeedbackStatus
) -> list[OrderFeedback]:
    result = await session.execute(
        select(OrderFeedbackORM).where(OrderFeedbackORM.status == status.value)
    )
    return [_orm_to_domain(row) for row in result.scalars().all()]


async def update_sentiment(
    session: AsyncSession,
    feedback_id: uuid.UUID,
    star_rating: int,
    comment: str | None,
    sentiment: Sentiment,
    responded_at: datetime,
) -> None:
    await session.execute(
        update(OrderFeedbackORM)
        .where(OrderFeedbackORM.id == feedback_id)
        .values(
            star_rating=star_rating,
            comment=comment,
            sentiment=sentiment.value,
            responded_at=responded_at,
        )
    )
    await session.flush()


async def update_status(
    session: AsyncSession,
    feedback_id: uuid.UUID,
    status: FeedbackStatus,
    reminder_sent_at: datetime | None = None,
) -> None:
    values: dict[str, Any] = {"status": status.value}
    if reminder_sent_at is not None:
        values["reminder_sent_at"] = reminder_sent_at
    await session.execute(
        update(OrderFeedbackORM)
        .where(OrderFeedbackORM.id == feedback_id)
        .values(**values)
    )
    await session.flush()


async def list_all(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
) -> list[OrderFeedback]:
    result = await session.execute(
        select(OrderFeedbackORM)
        .order_by(OrderFeedbackORM.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_orm_to_domain(row) for row in result.scalars().all()]


async def list_with_order_and_customer(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    sentiment: str | None = None,
    status: str | None = None,
) -> list[FeedbackRow]:
    q = (
        select(
            OrderFeedbackORM,
            OrderORM.items_snapshot,
            CustomerORM.display_name,
            CustomerORM.phone_e164,
        )
        .join(OrderORM, OrderFeedbackORM.order_id == OrderORM.id)
        .join(CustomerORM, OrderFeedbackORM.customer_id == CustomerORM.id)
    )
    if sentiment is not None:
        q = q.where(OrderFeedbackORM.sentiment == sentiment)
    if status is not None:
        q = q.where(OrderFeedbackORM.status == status)
    q = q.order_by(OrderFeedbackORM.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return [
        FeedbackRow(
            feedback=_orm_to_domain(r[0]),
            items_snapshot=r[1] or [],
            customer_name=r[2],
            customer_phone=r[3],
        )
        for r in result.all()
    ]


async def count(
    session: AsyncSession,
    sentiment: str | None = None,
    status: str | None = None,
) -> int:
    q = select(func.count()).select_from(OrderFeedbackORM)
    if sentiment is not None:
        q = q.where(OrderFeedbackORM.sentiment == sentiment)
    if status is not None:
        q = q.where(OrderFeedbackORM.status == status)
    result = await session.execute(q)
    return result.scalar_one()


async def get_summary(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        select(
            func.count().filter(OrderFeedbackORM.sentiment == "good").label("good"),
            func.count().filter(OrderFeedbackORM.sentiment == "bad").label("bad"),
            func.count().filter(OrderFeedbackORM.sentiment == "neutral").label("neutral"),
            func.count().filter(OrderFeedbackORM.status == "no_response").label("no_response"),
            func.count().filter(OrderFeedbackORM.status == "pending").label("pending"),
        ).select_from(OrderFeedbackORM)
    )
    row = result.one()
    return {
        "good": row.good,
        "bad": row.bad,
        "neutral": row.neutral,
        "no_response": row.no_response,
        "pending": row.pending,
    }
