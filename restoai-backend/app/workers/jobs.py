"""RQ background jobs.

dispatcher_notify: fired by escalation_service when awaiting_human is set.
send_feedback_request: fired immediately after order confirmation.
send_feedback_reminder: fired 6 hours after feedback request if still pending.
mark_feedback_no_response: fired 24 hours after reminder if still no reply.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


# ── Dispatcher notification ───────────────────────────────────────────────────

def dispatcher_notify(conversation_id: str) -> None:
    """Notify the dispatcher via Telegram when a customer needs human help."""
    asyncio.run(_async_notify(conversation_id))


async def _async_notify(conversation_id: str) -> None:
    import uuid as _uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from telegram import Bot

    from app.infra.logging import configure_logging
    from app.infra.settings import get_settings

    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    if not settings.DISPATCHER_TELEGRAM_CHAT_ID:
        logger.info(
            "dispatcher_notify_skipped_no_chat_id",
            extra={"conversation_id": conversation_id},
        )
        return

    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with factory() as session:
            from sqlalchemy import select

            from app.db.models import Conversation as ConvORM
            from app.db.models import Customer as CustomerORM

            cid = _uuid.UUID(conversation_id)
            result = await session.execute(
                select(ConvORM, CustomerORM)
                .join(CustomerORM, ConvORM.customer_id == CustomerORM.id)
                .where(ConvORM.id == cid)
            )
            row = result.one_or_none()

        if row is None:
            logger.warning(
                "dispatcher_notify_conversation_not_found",
                extra={"conversation_id": conversation_id},
            )
            return

        conv, customer = row
        customer_name = customer.display_name or "Unknown"
        customer_phone = customer.phone_e164 or "No phone on file"
        short_id = conversation_id[:8].upper()

        message = (
            "🚨 <b>Customer needs help!</b>\n\n"
            f"👤 {customer_name}\n"
            f"📞 {customer_phone}\n\n"
            "They've reached the 3-strike limit and need a human dispatcher.\n\n"
            f"<code>Conversation: {short_id}</code>"
        )

        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=int(settings.DISPATCHER_TELEGRAM_CHAT_ID),
            text=message,
            parse_mode="HTML",
        )
        logger.info(
            "dispatcher_notified",
            extra={"conversation_id": conversation_id, "customer": customer_name},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "dispatcher_notify_failed",
            extra={"conversation_id": conversation_id, "error": str(exc)},
        )
    finally:
        await engine.dispose()


# ── Feedback request ──────────────────────────────────────────────────────────

def enqueue_feedback_request(order_id: str) -> None:
    """Enqueue feedback request immediately after order confirmation."""
    try:
        import redis as sync_redis
        from rq import Queue

        from app.infra.settings import get_settings

        settings = get_settings()
        conn = sync_redis.from_url(settings.REDIS_URL)
        q = Queue(connection=conn)
        q.enqueue(
            send_feedback_request,
            order_id,
            job_id=f"feedback_request_{order_id}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("enqueue_feedback_request_failed", extra={"order_id": order_id, "error": str(exc)})


def send_feedback_request(order_id: str) -> None:
    """RQ job: send the feedback message to the customer via Telegram."""
    asyncio.run(_send_feedback_request_async(order_id))


async def _send_feedback_request_async(order_id: str) -> None:
    import uuid as _uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

    from app.domain.feedback import FeedbackStatus
    from app.infra.logging import configure_logging
    from app.infra.settings import get_settings
    from app.repositories import feedback_repo, order_repo

    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with factory() as session:
            oid = _uuid.UUID(order_id)
            result = await order_repo.get(session, oid)
            if result is None:
                logger.warning("feedback_request_order_not_found", extra={"order_id": order_id})
                return
            order, customer = result

            if customer.telegram_user_id is None:
                logger.info("feedback_request_no_telegram", extra={"order_id": order_id})
                return

            feedback = await feedback_repo.create(session, order.id, customer.id, None)
            await session.commit()

            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            message = (
                f"Hi {customer.display_name or 'there'}! 👋\n\n"
                f"Thank you for your order at Lakkis Farm. "
                f"How was your experience?\n\n"
                f"Please rate us:"
            )
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⭐", callback_data=f"feedback:{feedback.id}:1"),
                    InlineKeyboardButton("⭐⭐", callback_data=f"feedback:{feedback.id}:2"),
                    InlineKeyboardButton("⭐⭐⭐", callback_data=f"feedback:{feedback.id}:3"),
                    InlineKeyboardButton("⭐⭐⭐⭐", callback_data=f"feedback:{feedback.id}:4"),
                    InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f"feedback:{feedback.id}:5"),
                ]
            ])
            await bot.send_message(
                chat_id=customer.telegram_user_id,
                text=message,
                reply_markup=keyboard,
            )

            logger.info("feedback_request_sent", extra={"order_id": order_id, "feedback_id": str(feedback.id)})

            enqueue_feedback_reminder(order_id, str(feedback.id))
    except Exception as exc:  # noqa: BLE001
        logger.exception("send_feedback_request_failed", extra={"order_id": order_id, "error": str(exc)})
    finally:
        await engine.dispose()


# ── Feedback reminder ─────────────────────────────────────────────────────────

def enqueue_feedback_reminder(order_id: str, feedback_id: str) -> None:
    """Enqueue a reminder job to run 6 hours after the initial feedback request."""
    try:
        from datetime import timedelta

        import redis as sync_redis
        from rq import Queue

        from app.infra.settings import get_settings

        settings = get_settings()
        conn = sync_redis.from_url(settings.REDIS_URL)
        q = Queue(connection=conn)
        q.enqueue_in(
            timedelta(hours=6),
            send_feedback_reminder,
            order_id,
            feedback_id,
            job_id=f"feedback_reminder_{order_id}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "enqueue_feedback_reminder_failed",
            extra={"order_id": order_id, "feedback_id": feedback_id, "error": str(exc)},
        )


def send_feedback_reminder(order_id: str, feedback_id: str) -> None:
    """RQ job: send reminder if feedback is still pending after 6 hours."""
    asyncio.run(_send_feedback_reminder_async(order_id, feedback_id))


async def _send_feedback_reminder_async(order_id: str, feedback_id: str) -> None:
    import uuid as _uuid
    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

    from app.domain.feedback import FeedbackStatus
    from app.infra.logging import configure_logging
    from app.infra.settings import get_settings
    from app.repositories import feedback_repo, order_repo

    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with factory() as session:
            fid = _uuid.UUID(feedback_id)
            feedback = await feedback_repo.get_by_id(session, fid)
            if feedback is None or feedback.status != FeedbackStatus.PENDING:
                return

            oid = _uuid.UUID(order_id)
            result = await order_repo.get(session, oid)
            if result is None:
                return
            _, customer = result

            if customer.telegram_user_id is None:
                return

            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⭐", callback_data=f"feedback:{fid}:1"),
                    InlineKeyboardButton("⭐⭐", callback_data=f"feedback:{fid}:2"),
                    InlineKeyboardButton("⭐⭐⭐", callback_data=f"feedback:{fid}:3"),
                    InlineKeyboardButton("⭐⭐⭐⭐", callback_data=f"feedback:{fid}:4"),
                    InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f"feedback:{fid}:5"),
                ]
            ])
            await bot.send_message(
                chat_id=customer.telegram_user_id,
                text=(
                    "Just a reminder — we'd love to hear about your experience at "
                    "Lakkis Farm! How was your order? ⭐"
                ),
                reply_markup=keyboard,
            )

            now = datetime.now(tz=UTC)
            await feedback_repo.update_status(
                session, fid, FeedbackStatus.PENDING, reminder_sent_at=now
            )
            await session.commit()

            logger.info("feedback_reminder_sent", extra={"feedback_id": feedback_id})

            _enqueue_no_response_mark(order_id, feedback_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "send_feedback_reminder_failed",
            extra={"feedback_id": feedback_id, "error": str(exc)},
        )
    finally:
        await engine.dispose()


def _enqueue_no_response_mark(order_id: str, feedback_id: str) -> None:
    """Enqueue a job 24 hours after reminder to mark feedback as no_response."""
    try:
        from datetime import timedelta

        import redis as sync_redis
        from rq import Queue

        from app.infra.settings import get_settings

        settings = get_settings()
        conn = sync_redis.from_url(settings.REDIS_URL)
        q = Queue(connection=conn)
        q.enqueue_in(
            timedelta(hours=24),
            mark_feedback_no_response,
            feedback_id,
            job_id=f"feedback_no_response_{order_id}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "enqueue_no_response_failed",
            extra={"feedback_id": feedback_id, "error": str(exc)},
        )


def mark_feedback_no_response(feedback_id: str) -> None:
    """RQ job: mark feedback as no_response if customer never replied."""
    asyncio.run(_mark_feedback_no_response_async(feedback_id))


async def _mark_feedback_no_response_async(feedback_id: str) -> None:
    import uuid as _uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.domain.feedback import FeedbackStatus
    from app.infra.logging import configure_logging
    from app.infra.settings import get_settings
    from app.repositories import feedback_repo

    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with factory() as session:
            fid = _uuid.UUID(feedback_id)
            feedback = await feedback_repo.get_by_id(session, fid)
            if feedback is None or feedback.status != FeedbackStatus.PENDING:
                return
            await feedback_repo.update_status(session, fid, FeedbackStatus.NO_RESPONSE)
            await session.commit()
            logger.info("feedback_marked_no_response", extra={"feedback_id": feedback_id})
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "mark_feedback_no_response_failed",
            extra={"feedback_id": feedback_id, "error": str(exc)},
        )
    finally:
        await engine.dispose()
