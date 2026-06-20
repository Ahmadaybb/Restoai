"""Feedback domain models — 003-feedback."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class FeedbackStatus(StrEnum):
    PENDING = "pending"
    RECEIVED = "received"
    NO_RESPONSE = "no_response"


class Sentiment(StrEnum):
    GOOD = "good"
    BAD = "bad"
    NEUTRAL = "neutral"


class OrderFeedback(BaseModel):
    id: UUID
    order_id: UUID
    customer_id: UUID
    conversation_id: UUID | None = None
    star_rating: int | None = None
    comment: str | None = None
    sentiment: Sentiment | None = None
    status: FeedbackStatus
    feedback_requested_at: datetime
    reminder_sent_at: datetime | None = None
    responded_at: datetime | None = None
    created_at: datetime
