"""FeedbackService — business logic for customer feedback collection."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.feedback import FeedbackStatus, OrderFeedback, Sentiment
from app.repositories import feedback_repo


async def get_by_id(session: AsyncSession, feedback_id: UUID) -> OrderFeedback | None:
    return await feedback_repo.get_by_id(session, feedback_id)


async def record_feedback_response(
    session: AsyncSession,
    feedback_id: UUID,
    star_rating: int,
    comment: str | None,
    sentiment: Sentiment,
) -> None:
    now = datetime.now(tz=UTC)
    await feedback_repo.update_sentiment(
        session,
        feedback_id,
        star_rating=star_rating,
        comment=comment,
        sentiment=sentiment,
        responded_at=now,
    )
    await feedback_repo.update_status(session, feedback_id, FeedbackStatus.RECEIVED)
    await session.commit()


async def list_feedback(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    sentiment: str | None = None,
    status: str | None = None,
) -> list[Any]:
    return await feedback_repo.list_with_order_and_customer(
        session, limit=limit, offset=offset, sentiment=sentiment, status=status
    )


async def count_feedback(
    session: AsyncSession,
    sentiment: str | None = None,
    status: str | None = None,
) -> int:
    return await feedback_repo.count(session, sentiment=sentiment, status=status)


async def get_summary(session: AsyncSession) -> dict[str, int]:
    return await feedback_repo.get_summary(session)
