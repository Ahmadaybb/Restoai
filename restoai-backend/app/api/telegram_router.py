"""Telegram inbound router — webhook + polling integration.

Handles: /start, text messages, contact shares, location shares,
confirm/edit/fulfillment/saved_address callback queries, and
reservation callbacks (res_seating:*, res_date_confirm:*, res_date_retry).

contracts/telegram_webhook.md; FR-001, FR-009, FR-010, FR-013,
FR-014, FR-016, FR-018.
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import ExternalDependencyError, OrderValidationCode, OrderValidationError
from app.domain.language import Language
from app.domain.reservation import SeatingPreference
from app.infra import draft_store
from app.infra.redaction import redact
from app.services import (
    conversation_service,
    customer_service,
    order_draft_service,
    order_service,
    reservation_draft_service,
    reservation_prompts,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telegram"])


async def _dispatch_update(app: object, update_data: dict[str, Any]) -> None:
    """Background task: processes a Telegram update dict."""
    from app.api.deps import get_session as _gs

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

    # T086: auto-populate display_name from Telegram first_name (FR-012)
    tg_first_name = ""
    if "message" in data:
        tg_first_name = data["message"].get("from", {}).get("first_name", "")
    elif "callback_query" in data:
        tg_first_name = data["callback_query"].get("from", {}).get("first_name", "")
    if tg_first_name and not customer.display_name:
        await customer_service.set_display_name(session, customer.id, tg_first_name)
        customer = customer.model_copy(update={"display_name": tg_first_name})

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

        # Location share (FR-010, T088: fresh location also saved to Postgres)
        if "location" in msg:
            lat = msg["location"]["latitude"]
            lon = msg["location"]["longitude"]
            await order_draft_service.attach_location(customer.id, lat, lon, session=session)
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
            # Gate on fulfillment and address before placing the order
            try:
                await order_draft_service.validate_ready_to_confirm(customer.id)
            except OrderValidationError as ve:
                if ve.code == OrderValidationCode.MISSING_FULFILLMENT:
                    buttons = [
                        {"label": "🛵 Delivery", "callback_data": "fulfillment:delivery"},
                        {"label": "🏪 Pickup", "callback_data": "fulfillment:pickup"},
                    ]
                    await telegram.send_message(
                        chat_id=chat_id,
                        text="How would you like to receive your order?",
                        buttons=buttons,
                    )
                elif ve.code == OrderValidationCode.MISSING_ADDRESS:
                    if customer.addresses:
                        addr_buttons = [
                            {
                                "label": f"📍 {(a.text_value or 'Saved location')[:40]}",
                                "callback_data": f"saved_address:{a.id}",
                            }
                            for a in customer.addresses
                        ]
                        addr_buttons.append(
                            {"label": "🆕 New address", "callback_data": "new_address"}
                        )
                        await telegram.send_message(
                            chat_id=chat_id,
                            text="Choose a delivery address:",
                            buttons=addr_buttons,
                        )
                    else:
                        await telegram.send_message(
                            chat_id=chat_id,
                            text="🛵 Please share your delivery address.",
                        )
                else:
                    await telegram.send_message(
                        chat_id=chat_id,
                        text="Sorry, there's an issue with your order. Please try again.",
                    )
                return
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
                # T087: offer saved addresses as one-tap buttons (FR-013)
                if customer.addresses:
                    addr_buttons = [
                        {
                            "label": f"📍 {(a.text_value or 'Saved location')[:40]}",
                            "callback_data": f"saved_address:{a.id}",
                        }
                        for a in customer.addresses
                    ]
                    addr_buttons.append(
                        {"label": "🆕 New address", "callback_data": "new_address"}
                    )
                    await telegram.send_message(
                        chat_id=chat_id,
                        text="Choose a delivery address:",
                        buttons=addr_buttons,
                    )
                else:
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
                draft = await order_draft_service.select_saved_address(customer.id, addr)
                await telegram.send_message(
                    chat_id=chat_id,
                    text=f"✅ Using saved address: {addr.text_value or 'saved location'}",
                )
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
            else:
                await telegram.send_message(
                    chat_id=chat_id,
                    text="Address not found. Please enter a new address.",
                )

        elif cq_data.startswith("res_seating:"):
            await _handle_res_seating_callback(
                cq_data, customer, chat_id, telegram, session, llm
            )

        elif cq_data.startswith("res_date_confirm:"):
            # res_date_confirm:{customer_id}:{iso_date}
            parts = cq_data.split(":", 2)
            if len(parts) == 3 and llm is not None:
                iso_date = parts[2]
                date = _dt.date.fromisoformat(iso_date)
                res_draft = await reservation_draft_service.get_draft(customer.id)
                lang = res_draft.language if res_draft else Language.EN
                await reservation_draft_service.collect_field(customer.id, "date", date)
                await conversation_service.continue_reservation_flow(
                    session, customer, chat_id, telegram, llm, lang
                )

        elif cq_data == "res_date_retry":
            res_draft = await reservation_draft_service.get_draft(customer.id)
            lang = res_draft.language if res_draft else Language.EN
            await draft_store.put_chat_state(customer.id, {"waiting_for": "reservation_date"})
            await telegram.send_message(
                chat_id=chat_id,
                text=reservation_prompts.DATE.get(lang, reservation_prompts.DATE[Language.EN]),
            )

        elif cq_data == "new_address":
            # T087: customer chose to enter a fresh address (FR-015)
            await telegram.send_message(
                chat_id=chat_id,
                text="📍 Please share your delivery address.",
            )


async def _handle_res_seating_callback(
    cq_data: str,
    customer: Any,
    chat_id: int,
    telegram: Any,
    session: AsyncSession,
    llm: Any,
) -> None:
    """Route res_seating:* callback to the appropriate seating sub-step. T024, FR-006."""
    seating_val = cq_data.split(":", 1)[1]
    res_draft = await reservation_draft_service.get_draft(customer.id)
    lang: Language = res_draft.language if res_draft else Language.EN
    ar = lang in (Language.AR_LB, Language.ARABIZI)

    if seating_val == "indoor":
        await draft_store.put_chat_state(
            customer.id, {"waiting_for": "reservation_seating_smoking"}
        )
        buttons = (
            reservation_prompts.SMOKING_BUTTONS_AR if ar else reservation_prompts.SMOKING_BUTTONS_EN
        )
        await telegram.send_message(
            chat_id=chat_id,
            text=reservation_prompts.SMOKING.get(lang, reservation_prompts.SMOKING[Language.EN]),
            buttons=buttons,
        )

    elif seating_val == "outdoor":
        await draft_store.put_chat_state(
            customer.id, {"waiting_for": "reservation_seating_terrace"}
        )
        buttons = (
            reservation_prompts.TERRACE_BUTTONS_AR if ar else reservation_prompts.TERRACE_BUTTONS_EN
        )
        await telegram.send_message(
            chat_id=chat_id,
            text=reservation_prompts.TERRACE.get(lang, reservation_prompts.TERRACE[Language.EN]),
            buttons=buttons,
        )

    elif seating_val in ("indoor_smoking", "indoor_non_smoking", "outdoor_non_terrace"):
        sp_map = {
            "indoor_smoking": SeatingPreference.INDOOR_SMOKING,
            "indoor_non_smoking": SeatingPreference.INDOOR_NON_SMOKING,
            "outdoor_non_terrace": SeatingPreference.OUTDOOR_NON_TERRACE,
        }
        await reservation_draft_service.collect_field(
            customer.id, "seating_preference", sp_map[seating_val]
        )
        if llm is not None:
            await conversation_service.continue_reservation_flow(
                session, customer, chat_id, telegram, llm, lang
            )

    elif seating_val == "outdoor_terrace":
        # Save outdoor_terrace; _next_step_or_confirm raises TERRACE_TOO_LARGE if
        # party_size > 5 → sends terrace block message (FR-006, T023).
        await reservation_draft_service.collect_field(
            customer.id, "seating_preference", SeatingPreference.OUTDOOR_TERRACE
        )
        if llm is not None:
            await conversation_service.continue_reservation_flow(
                session, customer, chat_id, telegram, llm, lang
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
