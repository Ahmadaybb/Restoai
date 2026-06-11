"""Telegram inbound router — webhook + polling integration.

Handles: /start, text messages, contact shares, location shares,
confirm/edit/fulfillment/saved_address callback queries.

contracts/telegram_webhook.md; FR-001, FR-009, FR-010, FR-013,
FR-014, FR-016, FR-018.
"""
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import ExternalDependencyError
from app.infra.redaction import redact
from app.services import (
    conversation_service,
    customer_service,
    order_draft_service,
    order_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telegram"])


async def _dispatch_update(app: object, update_data: dict[str, Any]) -> None:
    """Background task: processes a Telegram update dict."""
    from app.db.engine import get_session as _gs

    session_gen = _gs()
    session: AsyncSession = await session_gen.__anext__()
    try:
        await _process_update(app, session, update_data)
        await session.commit()
    except Exception as exc:
        logger.error("telegram_dispatch_error", extra={"error": redact(str(exc))})
        await session.rollback()
    finally:
        try:
            await session_gen.aclose()
        except Exception:  # noqa: BLE001,S110
            pass


async def _process_update(
    app: object, session: AsyncSession, data: dict[str, Any]
) -> None:
    state = getattr(app, "state", None)
    telegram = getattr(state, "telegram", None)
    llm = getattr(state, "llm", None)
    embedder = getattr(state, "embedder", None)

    # Resolve customer from telegram user
    tg_user_id: int | None = None
    chat_id: int | None = None

    if "message" in data:
        msg = data["message"]
        tg_user_id = msg.get("from", {}).get("id")
        chat_id = msg.get("chat", {}).get("id")
    elif "callback_query" in data:
        cq = data["callback_query"]
        tg_user_id = cq.get("from", {}).get("id")
        chat_id = cq.get("message", {}).get("chat", {}).get("id")

    if not tg_user_id or not chat_id or telegram is None:
        return

    customer = await customer_service.get_or_create_anonymous(session, tg_user_id)

    if "message" in data:
        msg = data["message"]

        # /start command
        if msg.get("text", "").strip() == "/start":
            await conversation_service.on_start(session, customer, chat_id, telegram)
            return

        # Contact share (FR-014 phone bind)
        if "contact" in msg:
            phone = msg["contact"].get("phone_number", "")
            if phone and not phone.startswith("+"):
                phone = f"+{phone}"
            await customer_service.bind_phone_from_contact(session, customer.id, phone)
            await telegram.send_message(
                chat_id=chat_id,
                text="✅ Phone number saved. You can now confirm your orders.",
            )
            return

        # Location share (FR-010)
        if "location" in msg:
            lat = msg["location"]["latitude"]
            lon = msg["location"]["longitude"]
            await order_draft_service.attach_location(customer.id, lat, lon)
            await telegram.send_message(
                chat_id=chat_id,
                text="📍 Location saved! Would you like to confirm your order?",
            )
            return

        # Plain text message
        text = msg.get("text", "")
        if text and llm is not None:
            await conversation_service.handle_text(
                session, customer, chat_id, text, telegram, llm, embedder
            )

    elif "callback_query" in data:
        cq = data["callback_query"]
        cq_data: str = cq.get("data", "")

        if cq_data.startswith("confirm:"):
            draft_id = UUID(cq_data.split(":", 1)[1])
            try:
                order = await order_service.confirm(session, customer, draft_id)
                await telegram.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ Order confirmed! Your order #{str(order.id)[:8]} "
                        "is being reviewed by our team."
                    ),
                )
            except ExternalDependencyError as exc:
                logger.error("confirm_failed", extra={"error": redact(str(exc))})
                await telegram.send_message(
                    chat_id=chat_id,
                    text="Sorry, I couldn't confirm your order. Please try again.",
                )

        elif cq_data.startswith("edit:"):
            draft_id = UUID(cq_data.split(":", 1)[1])
            await order_draft_service.reopen_for_edit(customer.id, draft_id)
            await telegram.send_message(
                chat_id=chat_id,
                text="✏️ No problem! What would you like to change?",
            )

        elif cq_data.startswith("fulfillment:"):
            mode = cq_data.split(":", 1)[1]
            draft = await order_draft_service.set_fulfillment(customer.id, mode)
            if mode == "delivery":
                await telegram.send_message(
                    chat_id=chat_id,
                    text="🛵 Delivery selected. Please share your address.",
                )
            else:
                if llm is not None:
                    from app.domain.tools import RenderReadbackIn
                    from app.services.tools.render_readback import render_readback
                    rb = await render_readback(
                        RenderReadbackIn(draft=draft, language=draft.language),
                        llm=llm,
                    )
                    await telegram.send_message(
                        chat_id=chat_id,
                        text=rb.text,
                        buttons=[b.model_dump() for b in rb.buttons],
                    )

        elif cq_data.startswith("saved_address:"):
            addr_id = UUID(cq_data.split(":", 1)[1])
            addr = next(
                (a for a in customer.addresses if a.id == addr_id), None
            )
            if addr:
                await order_draft_service.select_saved_address(customer.id, addr)
                await telegram.send_message(
                    chat_id=chat_id,
                    text=f"✅ Using saved address: {addr.text_value or 'saved location'}",
                )
            else:
                await telegram.send_message(
                    chat_id=chat_id,
                    text="Address not found. Please enter a new address.",
                )


@router.post("/telegram/webhook/{secret_path}")
async def telegram_webhook(
    secret_path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    telegram = request.app.state.telegram

    # Secret path validation
    from app.infra.settings import get_settings
    settings = get_settings()
    if secret_path != settings.TELEGRAM_WEBHOOK_SECRET_PATH:
        raise HTTPException(status_code=404)

    # X-Telegram-Bot-Api-Secret-Token header validation
    if x_telegram_bot_api_secret_token and settings.TELEGRAM_WEBHOOK_SECRET:
        if not telegram.verify_webhook_secret(x_telegram_bot_api_secret_token):
            logger.warning("webhook_secret_mismatch")
            raise HTTPException(status_code=401)

    body: dict[str, Any] = await request.json()
    background_tasks.add_task(_dispatch_update, request.app, body)
    return {"ok": "true"}
