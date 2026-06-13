"""ConversationService — orchestrates the full turn lifecycle.

Detect language → record Turn → classify intent → route to tool(s) →
render reply → record outbound Turn.

T051: parse_order → match_dish two-pass pipeline (FR-003, FR-005, FR-006).
T060: handle_text routing for US1 (order intent; query stub).
T062: on_start welcome flow (FR-001, FR-002).
T069: graceful degradation on ExternalDependencyError (FR-034).
T021/T022: Intent.RESERVATION branch and _handle_reservation_intent (FR-001, FR-002).
"""
from __future__ import annotations

import datetime as _dt
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clients import EmbeddingClient, LLMClient, MessengerClient
from app.domain.conversation import Turn
from app.domain.customer import Address, Customer
from app.domain.errors import ExternalDependencyError
from app.domain.language import Intent, Language
from app.domain.order import OrderItem
from app.domain.reservation import (
    Reservation,
    ReservationValidationCode,
    ReservationValidationError,
    SeatingPreference,
)
from app.domain.tools import (
    AnswerMenuQuestionIn,
    ExtractReservationFieldsIn,
    MatchDishIn,
    ParseOrderIn,
    RenderReadbackIn,
    RenderReservationConfirmationIn,
)
from app.infra import draft_store
from app.infra.intent_classifier import classify
from app.infra.redaction import redact
from app.repositories import transcript_repo
from app.services import (
    customer_service,
    order_draft_service,
    reservation_draft_service,
    reservation_prompts,
    reservation_service,
)
from app.services.language_service import detect as lang_detect
from app.services.language_service import reply_language
from app.services.tools import answer_menu_question as qa_tool
from app.services.tools import extract_reservation_fields as extract_res_tool
from app.services.tools import match_dish as match_dish_tool
from app.services.tools import parse_order as parse_order_tool
from app.services.tools import render_readback as readback_tool
from app.services.tools import render_reservation_confirmation as render_res_conf_tool

logger = logging.getLogger(__name__)

_MODIFICATION_KEYWORDS = frozenset({
    "change", "modify", "update", "edit", "reschedule", "adjust", "alter",
    "بدّل", "غيّر", "عدّل",
    "تعديل", "تغيير",
    "badal", "ghayyer", "t3adel",
})

# Degradation messages per language
_DEGRADATION = {
    Language.EN: (
        "I'm sorry, I'm having a technical issue right now. "
        "Please try again in a moment, or type 'help' to reach a human agent."
    ),
    Language.AR_LB: (
        "آسف، أنا أواجه مشكلة تقنية الآن. "
        "يرجى المحاولة مرة أخرى بعد لحظة، أو اكتب 'مساعدة' للتواصل مع موظف."
    ),
    Language.ARABIZI: (
        "Sorry, fi mshkle techneye hala2. "
        "Jrreb marra tene, aw ktob 'help' la tetwassal ma3 mowadhef."
    ),
}

_WELCOME_EN = (
    "👋 Welcome to Lakkis Farm! I'm your order assistant.\n\n"
    "🍽️ View our full menu here:\n"
    "https://menu.omegasoftware.ca/mlmksal\n\n"
    "Just tell me what you'd like to order!"
)
_WELCOME_AR = (
    "👋 أهلاً بك في لاكيس فارم! أنا مساعدك للطلبات.\n\n"
    "🍽️ شاهد قائمة طعامنا الكاملة هنا:\n"
    "https://menu.omegasoftware.ca/mlmksal\n\n"
    "فقط أخبرني بما تريد طلبه!"
)

_FULFILLMENT_PROMPT_EN = "Would you like 🛵 Delivery or 🏪 Pickup?"
_FULFILLMENT_PROMPT_AR = "هل تريد التوصيل 🛵 أم الاستلام 🏪؟"

_ADDRESS_PROMPT_EN = "Please share your delivery address."
_ADDRESS_PROMPT_AR = "يرجى مشاركة عنوان التوصيل."

_QUERY_STUB_EN = "Menu Q&A is coming soon! For now, feel free to place an order."
_QUERY_STUB_AR = "الإجابة على أسئلة القائمة ستكون متاحة قريباً! للآن، يسعدنا استقبال طلبك."

RESTAURANT_NAME = "Lakkis Farm"


async def on_start(
    session: AsyncSession,
    customer: Customer,
    telegram_chat_id: int,
    messenger: MessengerClient,
) -> None:
    """FR-001, FR-002: Send welcome + full menu on /start. Clears any active draft."""
    try:
        await draft_store.delete_draft(customer.id)
    except RuntimeError:
        pass  # Redis not initialised (e.g. in unit tests)
    text = _WELCOME_EN
    if customer.display_name:
        text = f"Welcome back, {customer.display_name}! 😊\n" + text

    await messenger.send_message(chat_id=telegram_chat_id, text=text)

    conv = await transcript_repo.get_or_create_conversation(session, customer.id)
    turn = Turn(
        conversation_id=conv.id,
        sender="bot",
        text=redact(text)[:4000],
        language=Language.EN,
    )
    await transcript_repo.append_turn(session, turn)
    await session.commit()


async def handle_text(
    session: AsyncSession,
    customer: Customer,
    telegram_chat_id: int,
    text: str,
    messenger: MessengerClient,
    llm: LLMClient,
    embedder: EmbeddingClient | None = None,
) -> None:
    """FR-001..FR-019, FR-028..FR-033: Main orchestration loop for text input."""
    # 1. Detect language
    detected = lang_detect(text)
    reply_lang = reply_language(detected)

    # 2. Get / create conversation, record inbound Turn
    conv = await transcript_repo.get_or_create_conversation(session, customer.id)
    intent_result, confidence = classify(text)

    inbound_turn = Turn(
        conversation_id=conv.id,
        sender="customer",
        text=redact(text),
        language=detected.language,
        intent=intent_result,
    )
    await transcript_repo.append_turn(session, inbound_turn)
    await customer_service.update_last_seen(session, customer.id)

    # T095: while awaiting_human, record turns but don't reply — the
    # dispatcher is the active agent for this conversation (FR-026).
    if conv.awaiting_human:
        await session.commit()
        return

    # 3. Route intent
    reply_text: str
    buttons: list[dict[str, str]] | None = None

    try:
        if intent_result in (Intent.ORDER, Intent.UNKNOWN):
            reply_text, buttons = await _handle_order_intent(
                session, customer, text, reply_lang, llm, conv.id
            )
        elif intent_result == Intent.QUERY:
            reply_text, buttons = await _handle_query_intent(
                session, text, reply_lang, llm, embedder
            )
        elif intent_result == Intent.RESERVATION:
            reply_text, buttons = await _handle_reservation_intent(
                session, customer, text, reply_lang, llm, conv.id
            )
        else:
            reply_text = _DEGRADATION.get(reply_lang, _DEGRADATION[Language.EN])
    except ExternalDependencyError as exc:
        logger.error(
            "external_dependency_error",
            extra={"dependency": exc.dependency, "error_detail": redact(str(exc))},
        )
        reply_text = _DEGRADATION.get(reply_lang, _DEGRADATION[Language.EN])

    # 4. Send reply
    await messenger.send_message(
        chat_id=telegram_chat_id,
        text=reply_text,
        buttons=buttons,
    )

    # 5. Record outbound Turn
    outbound_turn = Turn(
        conversation_id=conv.id,
        sender="bot",
        text=redact(reply_text),
        language=reply_lang,
    )
    await transcript_repo.append_turn(session, outbound_turn)
    await session.commit()


async def _handle_query_intent(
    session: AsyncSession,
    text: str,
    reply_lang: Language,
    llm: LLMClient,
    embedder: EmbeddingClient | None,
) -> tuple[str, list[dict[str, str]] | None]:
    """Route query intent to answer_menu_question (US2, FR-007, FR-008).

    Falls back to the stub when the embedder is unavailable (e.g., in tests
    that haven't loaded the embedding model or in US1-only deployments).
    The active OrderDraft is NOT touched here so ordering and Q&A share one
    conversation without losing the cart (FR-008).
    """
    if embedder is None:
        stub = _QUERY_STUB_AR if reply_lang == Language.AR_LB else _QUERY_STUB_EN
        return stub, None

    qa_result = await qa_tool.answer_menu_question(
        AnswerMenuQuestionIn(question=text, language=reply_lang),
        session=session,
        embedder=embedder,
        llm=llm,
    )
    return qa_result.answer, None


async def _handle_order_intent(
    session: AsyncSession,
    customer: Customer,
    text: str,
    reply_lang: Language,
    llm: LLMClient,
    conversation_id: UUID,
) -> tuple[str, list[dict[str, str]] | None]:
    """Two-pass parse_order → match_dish pipeline (T051)."""

    # If draft is awaiting a text delivery address, save it and skip order parsing.
    draft_check = await order_draft_service.get_draft(customer.id)
    if draft_check and draft_check.fulfillment == "delivery" and draft_check.address is None:
        address = Address(kind="text", text_value=text, customer_id=customer.id)
        updated_draft = await order_draft_service.attach_address(
            customer.id, address, session=session
        )
        readback = await readback_tool.render_readback(
            RenderReadbackIn(draft=updated_draft, language=reply_lang),
            llm=llm,
        )
        buttons = [b.model_dump() for b in readback.buttons]
        return readback.text, buttons

    # Detect language for the tool
    detected = lang_detect(text)

    parse_result = await parse_order_tool.parse_order(
        ParseOrderIn(text=text, language=detected.language),
        llm=llm,
    )

    # Second pass: try to resolve unresolved phrases via match_dish
    resolved_extra: list[OrderItem] = []
    still_unresolved: list[str] = []

    for phrase in parse_result.unresolved:
        match = await match_dish_tool.match_dish(
            MatchDishIn(phrase=phrase, language=detected.language),
            llm=llm,
        )
        if match.menu_item_id:
            resolved_extra.append(
                OrderItem(menu_item_id=match.menu_item_id, quantity=1)
            )
            await draft_store.reset_failcount(customer.id, "dish_match")
        else:
            still_unresolved.append(phrase)
            count = await draft_store.incr_failcount(customer.id, "dish_match")
            logger.info("dish_unresolved", extra={"phrase": phrase, "failcount": count})

    all_items = list(parse_result.items) + resolved_extra
    if all_items:
        await order_draft_service.add_items(customer.id, all_items)
        await draft_store.reset_failcount(customer.id, "order_parse")

    if still_unresolved:
        count = await draft_store.incr_failcount(customer.id, "order_parse")
        if reply_lang == Language.AR_LB:
            return (
                f"لم أتمكن من التعرف على: {', '.join(still_unresolved)}. "
                "هل يمكنك إعادة الصياغة؟",
                None,
            )
        return (
            f"I couldn't find: {', '.join(still_unresolved)}. "
            "Could you rephrase or check the menu?",
            None,
        )

    # Show readback whenever the draft has items; fulfillment/address are gated
    # at confirm time so the user sees their cart first.
    draft = await order_draft_service.get_draft(customer.id)
    if draft is None or not draft.items:
        if reply_lang == Language.AR_LB:
            return "ما الذي تريد طلبه؟", None
        return "What would you like to order?", None

    readback = await readback_tool.render_readback(
        RenderReadbackIn(draft=draft, language=reply_lang),
        llm=llm,
    )
    buttons = [b.model_dump() for b in readback.buttons]
    return readback.text, buttons


# ── Reservation collection helpers ───────────────────────────────────────────


def _res_prompt(d: dict[Language, str], lang: Language) -> str:
    return d.get(lang, d[Language.EN])


def _is_arabic(lang: Language) -> bool:
    return lang in (Language.AR_LB, Language.ARABIZI)


def _date_confirm_prompt(
    date: _dt.date,
    customer_id: UUID,
    lang: Language,
) -> tuple[str, list[dict[str, str]]]:
    """Return date read-back text + confirm/retry buttons. FR-009, T026."""
    date_str = date.strftime("%d %B %Y")
    iso_date = date.isoformat()
    tmpl = _res_prompt(reservation_prompts.DATE_CONFIRM_TMPL, lang)
    text = tmpl.format(date_str=date_str)
    buttons: list[dict[str, str]] = [
        {
            "label": "✅ Yes, that's correct",
            "callback_data": f"res_date_confirm:{customer_id}:{iso_date}",
        },
        {"label": "✏️ No, let me re-type", "callback_data": "res_date_retry"},
    ]
    return text, buttons


def _code_to_waiting_for(code: ReservationValidationCode) -> str:
    _MAP: dict[ReservationValidationCode, str] = {
        ReservationValidationCode.MISSING_DATE: "reservation_date",
        ReservationValidationCode.PAST_DATE: "reservation_date",
        ReservationValidationCode.MISSING_TIME: "reservation_time",
        ReservationValidationCode.MISSING_PARTY_SIZE: "reservation_party_size",
        ReservationValidationCode.PARTY_TOO_LARGE: "",
        ReservationValidationCode.MISSING_NAME: "reservation_name",
        ReservationValidationCode.MISSING_PHONE: "reservation_phone",
        ReservationValidationCode.MISSING_SEATING: "reservation_seating_indoor_outdoor",
        ReservationValidationCode.TERRACE_TOO_LARGE: "reservation_seating_reask",
    }
    return _MAP.get(code, "")


def _prompt_for_code(
    code: ReservationValidationCode,
    lang: Language,
) -> tuple[str, list[dict[str, str]] | None]:
    """Return (text, buttons) appropriate for the given missing-field code."""
    ar = _is_arabic(lang)
    rp = reservation_prompts

    if code == ReservationValidationCode.MISSING_DATE:
        return _res_prompt(rp.DATE, lang), None

    if code == ReservationValidationCode.PAST_DATE:
        return (
            _res_prompt(rp.DATE_PAST, lang) + "\n" + _res_prompt(rp.DATE, lang),
            None,
        )

    if code == ReservationValidationCode.MISSING_TIME:
        return _res_prompt(rp.TIME, lang), None

    if code == ReservationValidationCode.MISSING_PARTY_SIZE:
        return _res_prompt(rp.PARTY_SIZE, lang), None

    if code == ReservationValidationCode.PARTY_TOO_LARGE:
        return _res_prompt(rp.CALL_CENTER_REDIRECT, lang), None

    if code == ReservationValidationCode.MISSING_NAME:
        return _res_prompt(rp.NAME, lang), None

    if code == ReservationValidationCode.MISSING_PHONE:
        return _res_prompt(rp.PHONE, lang), None

    if code == ReservationValidationCode.MISSING_SEATING:
        buttons = rp.INDOOR_OUTDOOR_BUTTONS_AR if ar else rp.INDOOR_OUTDOOR_BUTTONS_EN
        return _res_prompt(rp.INDOOR_OUTDOOR, lang), buttons

    if code == ReservationValidationCode.TERRACE_TOO_LARGE:
        buttons = rp.TERRACE_REASK_BUTTONS_AR if ar else rp.TERRACE_REASK_BUTTONS_EN
        return _res_prompt(rp.TERRACE_BLOCK, lang), buttons

    return _DEGRADATION.get(lang, _DEGRADATION[Language.EN]), None


def _resend_seating_prompt(
    waiting_for: str,
    lang: Language,
) -> tuple[str, list[dict[str, str]] | None]:
    """Re-send seating buttons when user types text during a button step."""
    ar = _is_arabic(lang)
    rp = reservation_prompts

    if waiting_for == "reservation_seating_smoking":
        return (
            _res_prompt(rp.SMOKING, lang),
            rp.SMOKING_BUTTONS_AR if ar else rp.SMOKING_BUTTONS_EN,
        )
    if waiting_for == "reservation_seating_terrace":
        return (
            _res_prompt(rp.TERRACE, lang),
            rp.TERRACE_BUTTONS_AR if ar else rp.TERRACE_BUTTONS_EN,
        )
    if waiting_for == "reservation_seating_reask":
        return (
            _res_prompt(rp.TERRACE_BLOCK, lang),
            rp.TERRACE_REASK_BUTTONS_AR if ar else rp.TERRACE_REASK_BUTTONS_EN,
        )
    # reservation_modify_seating or default: re-send indoor/outdoor
    return (
        _res_prompt(rp.INDOOR_OUTDOOR, lang),
        rp.INDOOR_OUTDOOR_BUTTONS_AR if ar else rp.INDOOR_OUTDOOR_BUTTONS_EN,
    )


async def _next_step_or_confirm(
    session: AsyncSession,
    customer: Customer,
    lang: Language,
    llm: LLMClient,
) -> tuple[str, list[dict[str, str]] | None]:
    """Try to confirm if all fields collected; otherwise prompt for next missing field."""
    draft = await reservation_draft_service.get_draft(customer.id)
    if draft is None:
        return _res_prompt(reservation_prompts.DATE, lang), None

    try:
        draft.validate_ready_to_confirm()
    except ReservationValidationError as ve:
        wf = _code_to_waiting_for(ve.code)
        await draft_store.put_chat_state(customer.id, {"waiting_for": wf})
        return _prompt_for_code(ve.code, lang)

    # All fields valid — confirm the reservation
    confirmed = await reservation_service.confirm(session, customer.id)
    conf_out = await render_res_conf_tool.render_reservation_confirmation(
        RenderReservationConfirmationIn(reservation=confirmed, language=lang),
        llm=llm,
    )
    await draft_store.put_chat_state(customer.id, {"waiting_for": ""})
    return conf_out.text, None


async def continue_reservation_flow(
    session: AsyncSession,
    customer: Customer,
    chat_id: int,
    messenger: MessengerClient,
    llm: LLMClient,
    lang: Language,
) -> None:
    """Called from telegram_router after a reservation callback (seating/date) is handled."""
    text, buttons = await _next_step_or_confirm(session, customer, lang, llm)
    await messenger.send_message(chat_id=chat_id, text=text, buttons=buttons)


async def _handle_reservation_intent(
    session: AsyncSession,
    customer: Customer,
    text: str,
    lang: Language,
    llm: LLMClient,
    conversation_id: UUID,
) -> tuple[str, list[dict[str, str]] | None]:
    """FR-001, FR-002, FR-009: Reservation field-collection state machine.

    Reads waiting_for from chat_state, dispatches to sub-handlers, and either
    prompts for the next field or confirms the reservation when all fields are set.
    """
    chat_state = await draft_store.get_chat_state(customer.id) or {}
    waiting_for: str = chat_state.get("waiting_for", "")

    # ── Fresh start or re-entry ───────────────────────────────────────────────
    if not waiting_for or not waiting_for.startswith("reservation_"):
        # T037: detect modification intent before starting a new reservation
        if _looks_like_modification(text):
            reservations = await reservation_service.find_active_by_customer(session, customer.id)
            if reservations:
                if len(reservations) == 1:
                    return await _handle_modification_intent(
                        session, customer, text, lang, llm, reservations[0]
                    )
                # T035: multiple reservations → selection buttons
                await draft_store.put_chat_state(
                    customer.id, {"waiting_for": "reservation_select_for_modify"}
                )
                buttons = _build_reservation_select_buttons(reservations)
                return _res_prompt(reservation_prompts.SELECT_RESERVATION_MODIFY, lang), buttons

        draft = await reservation_draft_service.get_draft(customer.id)
        if draft is None:
            draft = await reservation_draft_service.start_draft(customer.id, lang)

        # Extract any fields the user supplied upfront
        extracted = await extract_res_tool.extract_reservation_fields(
            ExtractReservationFieldsIn(text=text, language=lang), llm
        )

        if extracted.party_size is not None:
            try:
                draft = await reservation_draft_service.collect_field(
                    customer.id, "party_size", extracted.party_size
                )
            except ReservationValidationError as _ve:
                await draft_store.put_chat_state(customer.id, {"waiting_for": ""})
                return _prompt_for_code(_ve.code, lang)
        if extracted.name is not None:
            draft = await reservation_draft_service.collect_field(
                customer.id, "name", extracted.name
            )
        if extracted.phone is not None:
            draft = await reservation_draft_service.collect_field(
                customer.id, "phone", extracted.phone
            )
        if extracted.time is not None:
            draft = await reservation_draft_service.collect_field(
                customer.id, "time", extracted.time
            )

        # Handle date — check for informal date (T026, FR-009)
        if extracted.date is not None:
            if extracted.date_is_informal:
                await draft_store.put_chat_state(
                    customer.id, {"waiting_for": "reservation_date_confirm"}
                )
                return _date_confirm_prompt(extracted.date, customer.id, lang)
            draft = await reservation_draft_service.collect_field(
                customer.id, "date", extracted.date
            )

        # Prefill name/phone from Customer record if still unset (FR-004)
        await reservation_draft_service.prefill_from_customer(customer.id, customer)

        return await _next_step_or_confirm(session, customer, lang, llm)

    # ── Waiting for date (text input) ─────────────────────────────────────────
    if waiting_for == "reservation_date":
        extracted = await extract_res_tool.extract_reservation_fields(
            ExtractReservationFieldsIn(text=text, language=lang), llm
        )
        if extracted.date is not None:
            if extracted.date_is_informal:
                await draft_store.put_chat_state(
                    customer.id, {"waiting_for": "reservation_date_confirm"}
                )
                return _date_confirm_prompt(extracted.date, customer.id, lang)
            await reservation_draft_service.collect_field(customer.id, "date", extracted.date)
            return await _next_step_or_confirm(session, customer, lang, llm)
        return _res_prompt(reservation_prompts.DATE, lang), None

    # ── Waiting for time ──────────────────────────────────────────────────────
    if waiting_for == "reservation_time":
        extracted = await extract_res_tool.extract_reservation_fields(
            ExtractReservationFieldsIn(text=text, language=lang), llm
        )
        if extracted.time is not None:
            await reservation_draft_service.collect_field(customer.id, "time", extracted.time)
            return await _next_step_or_confirm(session, customer, lang, llm)
        return _res_prompt(reservation_prompts.TIME, lang), None

    # ── Waiting for party size ────────────────────────────────────────────────
    if waiting_for == "reservation_party_size":
        extracted = await extract_res_tool.extract_reservation_fields(
            ExtractReservationFieldsIn(text=text, language=lang), llm
        )
        if extracted.party_size is not None:
            try:
                await reservation_draft_service.collect_field(
                    customer.id, "party_size", extracted.party_size
                )
            except ReservationValidationError as _ve:
                await draft_store.put_chat_state(customer.id, {"waiting_for": ""})
                return _prompt_for_code(_ve.code, lang)
            return await _next_step_or_confirm(session, customer, lang, llm)
        return _res_prompt(reservation_prompts.PARTY_SIZE, lang), None

    # ── Waiting for name (plain text) ─────────────────────────────────────────
    if waiting_for == "reservation_name":
        name = text.strip()
        if name:
            await reservation_draft_service.collect_field(customer.id, "name", name)
            return await _next_step_or_confirm(session, customer, lang, llm)
        return _res_prompt(reservation_prompts.NAME, lang), None

    # ── Waiting for phone (plain text) ────────────────────────────────────────
    if waiting_for == "reservation_phone":
        phone = text.strip()
        if phone:
            await reservation_draft_service.collect_field(customer.id, "phone", phone)
            return await _next_step_or_confirm(session, customer, lang, llm)
        return _res_prompt(reservation_prompts.PHONE, lang), None

    # ── Button-driven seating steps (user typed text instead of clicking) ─────
    if waiting_for in (
        "reservation_seating_indoor_outdoor",
        "reservation_seating_smoking",
        "reservation_seating_terrace",
        "reservation_seating_reask",
        "reservation_modify_seating",  # T034: text fallback during modification seating
    ):
        return _resend_seating_prompt(waiting_for, lang)

    # ── Modification: waiting for the user to state what to change (T037) ─────
    if waiting_for == "reservation_modify_pending":
        res_id_str: str = chat_state.get("modification_reservation_id", "")
        if res_id_str:
            res = await reservation_service.get_by_id(session, UUID(res_id_str))
            if res is not None:
                return await _handle_modification_intent(session, customer, text, lang, llm, res)
        await draft_store.put_chat_state(customer.id, {"waiting_for": ""})
        return _res_prompt(reservation_prompts.DATE, lang), None

    # ── Modification: re-send selection buttons when user types (T035) ────────
    if waiting_for == "reservation_select_for_modify":
        reservations = await reservation_service.find_active_by_customer(session, customer.id)
        if not reservations:
            return _res_prompt(reservation_prompts.NO_ACTIVE_RESERVATION, lang), None
        buttons = _build_reservation_select_buttons(reservations)
        return _res_prompt(reservation_prompts.SELECT_RESERVATION_MODIFY, lang), buttons

    # ── Unknown state — restart ───────────────────────────────────────────────
    await reservation_draft_service.start_draft(customer.id, lang)
    await draft_store.put_chat_state(customer.id, {"waiting_for": ""})
    return _res_prompt(reservation_prompts.DATE, lang), None


# ── Modification helpers ──────────────────────────────────────────────────────


def _looks_like_modification(text: str) -> bool:
    """Quick keyword scan to route modification intents before an LLM call. T037."""
    lower = text.lower()
    return any(kw in lower for kw in _MODIFICATION_KEYWORDS)


def _build_reservation_select_buttons(
    reservations: list[Reservation],
) -> list[dict[str, str]]:
    """Build res_select:{id} buttons labelled '{ref} — {day} {date} {time}'. T035, R9."""
    buttons = []
    for res in reservations:
        day = res.date.strftime("%a")
        date_str = res.date.strftime("%d %b")
        time_str = res.time.strftime("%I:%M %p").lstrip("0")
        label = f"{res.reference} — {day} {date_str} {time_str}"
        buttons.append({"label": label, "callback_data": f"res_select:{res.id}"})
    return buttons


async def _handle_modification_intent(
    session: AsyncSession,
    customer: Customer,
    text: str,
    lang: Language,
    llm: LLMClient,
    reservation: Reservation,
) -> tuple[str, list[dict[str, str]] | None]:
    """FR-013, FR-014, FR-015, FR-016: State machine for modifying an existing reservation.

    Called from _handle_reservation_intent (T037) and from the router after res_select: (T036).
    """
    # If text is empty (arriving from a callback), ask what to change
    if not text.strip():
        await draft_store.put_chat_state(
            customer.id,
            {
                "waiting_for": "reservation_modify_pending",
                "modification_reservation_id": str(reservation.id),
            },
        )
        return _res_prompt(reservation_prompts.MODIFY_WHICH_FIELD, lang), None

    # Extract the fields the user wants to change
    extracted = await extract_res_tool.extract_reservation_fields(
        ExtractReservationFieldsIn(text=text, language=lang), llm
    )

    fields: dict[str, object] = {}
    if extracted.date is not None:
        fields["date"] = extracted.date
    if extracted.time is not None:
        fields["time"] = extracted.time
    if extracted.party_size is not None:
        try:
            await reservation_draft_service.collect_field(
                customer.id, "party_size", extracted.party_size
            )
        except ReservationValidationError:
            # Reuse the same redirect guard as initial booking (PARTY_TOO_LARGE)
            await draft_store.put_chat_state(customer.id, {"waiting_for": ""})
            return _prompt_for_code(ReservationValidationCode.PARTY_TOO_LARGE, lang)
        fields["party_size"] = extracted.party_size

    if not fields:
        await draft_store.put_chat_state(
            customer.id,
            {
                "waiting_for": "reservation_modify_pending",
                "modification_reservation_id": str(reservation.id),
            },
        )
        return _res_prompt(reservation_prompts.MODIFICATION_NOTHING_EXTRACTED, lang), None

    try:
        updated = await reservation_service.modify(
            session, customer.id, reservation.id, fields
        )
    except ReservationValidationError as ve:
        if ve.code == ReservationValidationCode.TERRACE_TOO_LARGE:
            ar = _is_arabic(lang)
            rp = reservation_prompts
            await draft_store.put_chat_state(
                customer.id,
                {
                    "waiting_for": "reservation_modify_seating",
                    "modification_reservation_id": str(reservation.id),
                },
            )
            return (
                _res_prompt(rp.TERRACE_BLOCK, lang),
                rp.TERRACE_REASK_BUTTONS_AR if ar else rp.TERRACE_REASK_BUTTONS_EN,
            )
        return _prompt_for_code(ve.code, lang)

    conf_out = await render_res_conf_tool.render_reservation_confirmation(
        RenderReservationConfirmationIn(
            reservation=updated, language=lang, is_modification=True
        ),
        llm=llm,
    )
    await draft_store.put_chat_state(customer.id, {"waiting_for": ""})
    return conf_out.text, None


async def begin_modification(
    session: AsyncSession,
    customer: Customer,
    reservation_id: UUID,
    chat_id: int,
    messenger: MessengerClient,
    llm: LLMClient,
) -> None:
    """Public. Called from router after res_select: in modify context. T036."""
    res = await reservation_service.get_by_id(session, reservation_id)
    if res is None:
        await messenger.send_message(
            chat_id=chat_id,
            text="Sorry, that reservation could not be found.",
        )
        return
    text, buttons = await _handle_modification_intent(
        session, customer, "", res.language, llm, res
    )
    await messenger.send_message(chat_id=chat_id, text=text, buttons=buttons)


async def continue_modification_flow(
    session: AsyncSession,
    customer: Customer,
    reservation_id: UUID,
    seating_preference: SeatingPreference,
    chat_id: int,
    messenger: MessengerClient,
    llm: LLMClient,
    lang: Language,
) -> None:
    """Public. Called from router when user clicks a seating button during modification. T034."""
    try:
        updated = await reservation_service.modify(
            session, customer.id, reservation_id, {"seating_preference": seating_preference}
        )
    except ReservationValidationError as ve:
        if ve.code == ReservationValidationCode.TERRACE_TOO_LARGE:
            await draft_store.put_chat_state(
                customer.id,
                {
                    "waiting_for": "reservation_modify_seating",
                    "modification_reservation_id": str(reservation_id),
                },
            )
        text, buttons = _prompt_for_code(ve.code, lang)
        await messenger.send_message(chat_id=chat_id, text=text, buttons=buttons)
        return

    conf_out = await render_res_conf_tool.render_reservation_confirmation(
        RenderReservationConfirmationIn(
            reservation=updated, language=lang, is_modification=True
        ),
        llm=llm,
    )
    await draft_store.put_chat_state(customer.id, {"waiting_for": ""})
    await messenger.send_message(chat_id=chat_id, text=conf_out.text)
