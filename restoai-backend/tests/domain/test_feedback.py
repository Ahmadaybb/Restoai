"""Domain model tests for feedback enums and OrderFeedback Pydantic model."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.feedback import FeedbackStatus, OrderFeedback, Sentiment


# ── FeedbackStatus enum ───────────────────────────────────────────────────────

def test_feedback_status_pending_value() -> None:
    assert FeedbackStatus.PENDING == "pending"


def test_feedback_status_received_value() -> None:
    assert FeedbackStatus.RECEIVED == "received"


def test_feedback_status_no_response_value() -> None:
    assert FeedbackStatus.NO_RESPONSE == "no_response"


def test_feedback_status_str() -> None:
    assert str(FeedbackStatus.PENDING) == "pending"
    assert str(FeedbackStatus.RECEIVED) == "received"
    assert str(FeedbackStatus.NO_RESPONSE) == "no_response"


# ── Sentiment enum ────────────────────────────────────────────────────────────

def test_sentiment_good_value() -> None:
    assert Sentiment.GOOD == "good"


def test_sentiment_bad_value() -> None:
    assert Sentiment.BAD == "bad"


def test_sentiment_neutral_value() -> None:
    assert Sentiment.NEUTRAL == "neutral"


def test_sentiment_str() -> None:
    assert str(Sentiment.GOOD) == "good"
    assert str(Sentiment.BAD) == "bad"
    assert str(Sentiment.NEUTRAL) == "neutral"


# ── OrderFeedback model ───────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def test_order_feedback_minimal_valid() -> None:
    fb = OrderFeedback(
        id=uuid4(),
        order_id=uuid4(),
        customer_id=uuid4(),
        status=FeedbackStatus.PENDING,
        feedback_requested_at=_now(),
        created_at=_now(),
    )
    assert fb.star_rating is None
    assert fb.comment is None
    assert fb.sentiment is None
    assert fb.conversation_id is None
    assert fb.reminder_sent_at is None
    assert fb.responded_at is None


def test_order_feedback_with_all_fields() -> None:
    now = _now()
    fb = OrderFeedback(
        id=uuid4(),
        order_id=uuid4(),
        customer_id=uuid4(),
        conversation_id=uuid4(),
        star_rating=5,
        comment="Great food!",
        sentiment=Sentiment.GOOD,
        status=FeedbackStatus.RECEIVED,
        feedback_requested_at=now,
        reminder_sent_at=None,
        responded_at=now,
        created_at=now,
    )
    assert fb.star_rating == 5
    assert fb.comment == "Great food!"
    assert fb.sentiment == Sentiment.GOOD
    assert fb.status == FeedbackStatus.RECEIVED


def test_order_feedback_status_enum_coercion() -> None:
    fb = OrderFeedback(
        id=uuid4(),
        order_id=uuid4(),
        customer_id=uuid4(),
        status="received",  # type: ignore[arg-type]
        feedback_requested_at=_now(),
        created_at=_now(),
    )
    assert fb.status == FeedbackStatus.RECEIVED


def test_order_feedback_sentiment_enum_coercion() -> None:
    fb = OrderFeedback(
        id=uuid4(),
        order_id=uuid4(),
        customer_id=uuid4(),
        sentiment="bad",  # type: ignore[arg-type]
        status=FeedbackStatus.RECEIVED,
        feedback_requested_at=_now(),
        created_at=_now(),
    )
    assert fb.sentiment == Sentiment.BAD


def test_order_feedback_invalid_status_raises() -> None:
    with pytest.raises(Exception):
        OrderFeedback(
            id=uuid4(),
            order_id=uuid4(),
            customer_id=uuid4(),
            status="unknown_status",  # type: ignore[arg-type]
            feedback_requested_at=_now(),
            created_at=_now(),
        )
