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

_PRICE_QUESTION_KEYWORDS = frozenset({
    "price", "prices", "how much", "cost", "كم", "سعر", "بكم", "كم سعر",
})

_MODIFICATION_KEYWORDS = frozenset({
    "change", "modify", "update", "edit", "reschedule", "adjust", "alter",
    "بدّل", "غيّر", "عدّل",
    "تعديل", "تغيير",
    "badal", "ghayyer", "t3adel",
})

_CANCELLATION_KEYWORDS = frozenset({
    "cancel", "cancellation", "drop reservation", "delete reservation",
    "إلغاء", "إلغِ", "الغي", "الغ حجز",
    "ilghi", "ilghaa", "3am bilghi",
})

_START_OVER_KEYWORDS = frozenset({
    "start over", "start fresh", "start again", "clear cart", "clear order",
    "clear everything", "reset order", "empty cart", "wipe cart", "new order",
    "من الأول", "بدي ابدأ من أول", "امسح الطلب", "ابدأ من جديد", "الغ الطلب",
})

_QUESTION_WORDS = frozenset({
    "what", "how", "is", "are", "why", "when", "where", "which", "who",
    "do", "does", "can", "should", "tell", "explain",
    "كيف", "ما", "ماذا", "هل", "متى", "أين",
})

_PRONOUNS = frozenset({"it", "that", "this", "them", "those"})

# ── Upsell / recommendation data ─────────────────────────────────────────────

_DRINK_CATEGORIES = frozenset({
    "Cold Beverages", "Hot Beverages", "Fresh juice", "Laban",
})

# Ordered category → complementary categories to suggest (priority order)
_CATEGORY_PAIRINGS: dict[str, list[str]] = {
    "Salads":                              ["Sfiha Experts", "Hot Mezza"],
    "Cold Mezza":                          ["Sfiha Experts", "Hot Mezza"],
    "Hot Mezza":                           ["Salads", "Cold Mezza"],
    "Grills":                              ["Salads", "Cold Mezza"],
    "Main Course":                         ["Salads", "Cold Mezza"],
    "Breakfast":                           ["Sfiha Experts", "Fresh juice"],
    "Sfiha Experts":                       ["Salads", "Cold Mezza"],
    "Burgers":                             ["Salads", "Cold Mezza"],
    "Hot Sandwiches":                      ["Salads", "Cold Mezza"],
    "Cold Sandwiches":                     ["Salads", "Hot Mezza"],
    "Authentic Woodfire Tannour Manakish": ["Salads", "Cold Mezza"],
    "Fatteh":                              ["Salads"],
}

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

_WELCOME_EN = "👋 Welcome to Lakkis Farm! How can I help you today?"
_WELCOME_AR = "👋 أهلاً بك في لاكيس فارم! كيف يمكنني مساعدتك اليوم؟"

_START_BUTTONS_EN: list[dict[str, str]] = [
    {"label": "🍽️ Order Food", "callback_data": "start_action:order"},
    {"label": "📅 Reserve a Table", "callback_data": "start_action:reserve"},
]
_START_BUTTONS_AR: list[dict[str, str]] = [
    {"label": "🍽️ اطلب طعاماً", "callback_data": "start_action:order"},
    {"label": "📅 احجز طاولة", "callback_data": "start_action:reserve"},
]

_ORDER_PROMPT_EN = (
    "🍽️ View our full menu here:\n"
    "https://menu.omegasoftware.ca/mlmksal\n\n"
    "Just tell me what you'd like to order!"
)
_ORDER_PROMPT_AR = (
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
    """FR-001, FR-002: Send welcome + action buttons on /start. Clears any active draft."""
    try:
        await draft_store.delete_draft(customer.id)
    except RuntimeError:
        pass  # Redis not initialised (e.g. in unit tests)

    text = _WELCOME_EN
    buttons = _START_BUTTONS_EN
    if customer.display_name:
        text = f"Welcome back, {customer.display_name}! 😊\n" + text

    await messenger.send_message(chat_id=telegram_chat_id, text=text, buttons=buttons)

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
        try:
            active_chat_state = await draft_store.get_chat_state(customer.id) or {}
        except RuntimeError:
            active_chat_state = {}  # Redis not initialised (e.g. in unit tests)

        # Fokhara price follow-up: user asked about prices after the bot listed
        # the 4 clay-pot dishes — answer directly then clear the context.
        if active_chat_state.get("fokhara_context") and _looks_like_price_question(text):
            reply_text, buttons = await _handle_fokhara_price_query(reply_lang)
            new_state = {k: v for k, v in active_chat_state.items() if k != "fokhara_context"}
            try:
                await draft_store.put_chat_state(customer.id, new_state)
            except RuntimeError:
                pass
            # Skip normal routing — send directly
            await messenger.send_message(
                chat_id=telegram_chat_id, text=reply_text, buttons=buttons
            )
            outbound_turn = Turn(
                conversation_id=conv.id,
                sender="bot",
                text=redact(reply_text),
                language=reply_lang,
            )
            await transcript_repo.append_turn(session, outbound_turn)
            await session.commit()
            return

        active_waiting_for: str = active_chat_state.get("waiting_for", "")
        in_reservation_flow = active_waiting_for.startswith("reservation_")

        # Bug 3: if the reservation state machine is waiting but the input clearly
        # doesn't match the expected field, clear the stale wait state and fall
        # through to normal intent routing instead.
        if in_reservation_flow and not _input_matches_field(text, active_waiting_for):
            in_reservation_flow = False
            try:
                await draft_store.put_chat_state(
                    customer.id, {**active_chat_state, "waiting_for": ""}
                )
            except RuntimeError:
                pass

        # Fetch the bot's last 2 replies for RAG context (enables follow-up questions).
        recent_bot_turns: list[str] = []
        try:
            recent = await transcript_repo.get_recent_turns(session, conv.id, limit=6)
            recent_bot_turns = [t.text for t in recent if t.sender == "bot"][-2:]
        except Exception:
            pass

        if in_reservation_flow:
            reply_text, buttons = await _handle_reservation_intent(
                session, customer, text, reply_lang, llm, conv.id
            )
        elif intent_result == Intent.ORDER:
            reply_text, buttons = await _handle_order_intent(
                session, customer, text, reply_lang, llm, conv.id
            )
        elif intent_result == Intent.QUERY:
            # Short bare food names (e.g. "fattoush") are often classified as
            # QUERY but are actually ORDER — check before sending to RAG.
            if _looks_like_bare_food_order(text):
                reply_text, buttons = await _handle_order_intent(
                    session, customer, text, reply_lang, llm, conv.id
                )
            else:
                reply_text, buttons = await _handle_query_intent(
                    session, text, reply_lang, llm, embedder, recent_bot_turns
                )
                # Track which dish the customer just asked about so we can
                # resolve pronouns like "it" in their next order message.
                dish_name = _extract_dish_from_query(text)
                if dish_name:
                    try:
                        qs = await draft_store.get_chat_state(customer.id) or {}
                        await draft_store.put_chat_state(
                            customer.id, {**qs, "last_mentioned_dish": dish_name}
                        )
                    except RuntimeError:
                        pass
        elif intent_result == Intent.UNKNOWN:
            # If there's an active order draft, treat as order continuation.
            # If text is a short bare food name, also treat as ORDER.
            # Otherwise fall through to RAG.
            active_order_draft = await order_draft_service.get_draft(customer.id)
            if active_order_draft or _looks_like_bare_food_order(text):
                reply_text, buttons = await _handle_order_intent(
                    session, customer, text, reply_lang, llm, conv.id
                )
            else:
                reply_text, buttons = await _handle_query_intent(
                    session, text, reply_lang, llm, embedder, recent_bot_turns
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
    except Exception:
        logger.exception("handle_text_unexpected_error")
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


def _looks_like_price_question(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _PRICE_QUESTION_KEYWORDS)


def _looks_like_bare_food_order(text: str) -> bool:
    """Return True when text is a short food name (≤4 words, no question markers,
    and fuzzy-matches a menu item). Used to route QUERY/UNKNOWN intent to ORDER."""
    from app.repositories import menu_repo as _mr

    words = text.lower().split()
    if len(words) > 4:
        return False
    if text.strip().endswith("?"):
        return False
    if any(w in _QUESTION_WORDS for w in words):
        return False
    return bool(_mr.find_by_phrase(text))


async def _handle_fokhara_price_query(
    lang: Language,
) -> tuple[str, list[dict[str, str]] | None]:
    """Return prices for all four fokhara (clay pot) dishes."""
    from app.repositories import menu_repo

    dish_names_en = ["Meat Frikeh", "Meat Rice", "Chicken Frikeh", "Chicken Rice"]
    dish_names_ar = ["فريكة باللحم", "رز باللحم", "فريكة بالدجاج", "رز بالدجاج"]
    ar = lang in (Language.AR_LB, Language.ARABIZI)

    lines: list[str] = []
    for en_name, ar_name in zip(dish_names_en, dish_names_ar):
        item = next(
            (i for i in menu_repo.get_menu() if en_name.lower() in i.name_en.lower()),
            None,
        )
        price_str = f"${item.price_usd:.2f}" if item else "N/A"
        label = ar_name if ar else en_name
        lines.append(f"- {label} — {price_str}")

    if ar:
        return "إليك الأسعار:\n" + "\n".join(lines), None
    return "Here are the prices:\n" + "\n".join(lines), None


async def _handle_query_intent(
    session: AsyncSession,
    text: str,
    reply_lang: Language,
    llm: LLMClient,
    embedder: EmbeddingClient | None,
    recent_bot_turns: list[str] | None = None,
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
        AnswerMenuQuestionIn(
            question=text,
            language=reply_lang,
            recent_turns=recent_bot_turns or [],
        ),
        session=session,
        embedder=embedder,
        llm=llm,
    )
    return qa_result.answer, None


def _pick_recommendation(draft: "OrderDraft") -> "MenuItem | None":
    """Return one complementary menu item not already in the cart, or None."""
    from app.repositories import menu_repo as _mr

    ordered_ids = {item.menu_item_id for item in draft.items}
    ordered_cats: list[str] = []
    for item in draft.items:
        mi = _mr.get_item(item.menu_item_id)
        if mi and mi.category not in ordered_cats:
            ordered_cats.append(mi.category)

    for cat in ordered_cats:
        for target_cat in _CATEGORY_PAIRINGS.get(cat, []):
            already_has = False
            for i in draft.items:
                m = _mr.get_item(i.menu_item_id)
                if m and m.category == target_cat:
                    already_has = True
                    break
            if already_has:
                continue
            candidates = [
                mi for mi in _mr.get_menu()
                if mi.category == target_cat and mi.available and mi.id not in ordered_ids
            ]
            if candidates:
                return candidates[0]
    return None


def _has_drink(draft: "OrderDraft") -> bool:
    """Return True if the cart already contains a drink."""
    from app.repositories import menu_repo as _mr

    for item in draft.items:
        mi = _mr.get_item(item.menu_item_id)
        if mi and mi.category in _DRINK_CATEGORIES:
            return True
    return False


def _build_upsell(draft: "OrderDraft", lang: Language) -> str:
    """Return a 1–2 line upsell string, or empty string if nothing to suggest."""
    from app.repositories import menu_repo as _mr

    ar = lang in (Language.AR_LB, Language.ARABIZI)
    lines: list[str] = []

    rec = _pick_recommendation(draft)
    if rec:
        price = f"${rec.price_usd:.2f}"
        name = (rec.name_ar or rec.name_en) if ar else rec.name_en
        lines.append(
            f"💡 أنصح أيضاً بـ {name} — {price}" if ar
            else f"💡 You might also enjoy {rec.name_en} — {price}"
        )

    if not _has_drink(draft):
        all_items = _mr.get_menu()
        ayran = next(
            (mi for mi in all_items if mi.name_en.upper() == "AYRAN BOTTLE" and mi.available),
            None,
        )
        pepsi = next(
            (mi for mi in all_items if mi.name_en.upper() == "PEPSI" and mi.available),
            None,
        )
        if ayran and pepsi:
            if ar:
                lines.append(f"🥤 تريد مشروب؟ عنا {ayran.name_ar or ayran.name_en} أو {pepsi.name_en}")
            else:
                lines.append(f"🥤 Would you like a drink? We have Ayran Bottle or Pepsi!")
        elif ayran or pepsi:
            drink = ayran or pepsi
            name = (drink.name_ar or drink.name_en) if ar else drink.name_en  # type: ignore[union-attr]
            lines.append(
                f"🥤 تريد مشروب؟ جرّب {name}" if ar
                else f"🥤 Want a drink? Try {name}!"
            )

    return "\n".join(lines)


def _looks_like_phone(text: str) -> bool:
    digits = "".join(c for c in text if c.isdigit())
    return len(digits) >= 6


def _normalize_phone(raw: str) -> str | None:
    """Convert a raw phone input to E.164, or return None if not parseable."""
    import re as _re2
    raw = raw.strip()
    # Already E.164
    if _re2.match(r"^\+\d{8,15}$", raw):
        return raw
    digits = "".join(c for c in raw if c.isdigit())
    # Lebanese 8-digit mobile (starts with 3, 7, or 8)
    if len(digits) == 8 and digits[0] in "378":
        return f"+961{digits}"
    # +961 with country code already in digits: 96171234567
    if len(digits) == 11 and digits.startswith("961"):
        return f"+{digits}"
    # 00961XXXXXXXX
    if len(digits) == 13 and digits.startswith("00961"):
        return f"+{digits[2:]}"
    return None


import re as _re

_QUERY_STRIP_RE = _re.compile(
    r"^(what(?:'s| is| are)?(?: the)?|tell me about|describe|explain|how much is|price of|كم سعر|ما هو|ما هي)\s+",
    _re.IGNORECASE,
)


def _extract_dish_from_query(text: str) -> str | None:
    """Return the best menu item name found in a query string, or None."""
    from app.repositories import menu_repo as _mr

    clean = _QUERY_STRIP_RE.sub("", text.strip()).rstrip("?").strip()
    if not clean or len(clean.split()) > 5:
        return None
    matches = _mr.find_by_phrase(clean)
    return matches[0].name_en if matches else None


def _resolve_pronouns(text: str, last_dish: str | None) -> str:
    """Replace the first standalone pronoun in text with last_dish, if present."""
    if not last_dish:
        return text
    words = text.lower().split()
    if not any(w in _PRONOUNS for w in words):
        return text
    return _re.sub(
        r"\b(it|that|this|them|those)\b",
        last_dish,
        text,
        count=1,
        flags=_re.IGNORECASE,
    )


async def _handle_order_intent(
    session: AsyncSession,
    customer: Customer,
    text: str,
    reply_lang: Language,
    llm: LLMClient,
    conversation_id: UUID,
) -> tuple[str, list[dict[str, str]] | None]:
    """Two-pass parse_order → match_dish pipeline (T051)."""

    try:
        chat_state = await draft_store.get_chat_state(customer.id) or {}
    except RuntimeError:
        chat_state = {}

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

    # Check for start-over / clear cart request before parsing
    text_lower = text.lower().strip()
    if any(kw in text_lower for kw in _START_OVER_KEYWORDS):
        await order_draft_service.clear_items(customer.id)
        if reply_lang == Language.AR_LB:
            return "تم مسح طلبك 🗑️ ماذا تريد أن تطلب؟", None
        return "Cart cleared! 🗑️ What would you like to order?", None

    # Detect language for the tool
    detected = lang_detect(text)

    # Resolve pronouns like "it"/"that" using the last dish the bot discussed
    last_dish = chat_state.get("last_mentioned_dish")
    parse_text = _resolve_pronouns(text, last_dish)
    if last_dish and parse_text != text:
        # Clear the context so it doesn't affect future unrelated messages
        try:
            await draft_store.put_chat_state(
                customer.id, {k: v for k, v in chat_state.items() if k != "last_mentioned_dish"}
            )
        except RuntimeError:
            pass

    parse_result = await parse_order_tool.parse_order(
        ParseOrderIn(text=parse_text, language=detected.language),
        llm=llm,
    )

    # Handle remove_phrases — remove matched items from draft
    from app.repositories import menu_repo as _mr
    for phrase in parse_result.remove_phrases:
        matches = _mr.find_by_phrase(phrase)
        if matches:
            await order_draft_service.remove_item(customer.id, matches[0].id)
            logger.info("item_removed", extra={"phrase": phrase, "item_id": matches[0].id})

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

    # If only removes happened (no adds, no unresolved), show updated cart
    if not all_items and not still_unresolved and parse_result.remove_phrases:
        draft = await order_draft_service.get_draft(customer.id)
        if draft is None or not draft.items:
            if reply_lang == Language.AR_LB:
                return "تم حذف الصنف. طلبك فارغ الآن. ماذا تريد أن تطلب؟", None
            return "Item removed. Your cart is now empty. What would you like to order?", None
        readback = await readback_tool.render_readback(
            RenderReadbackIn(draft=draft, language=reply_lang), llm=llm
        )
        return readback.text, [b.model_dump() for b in readback.buttons]

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

        # T040: detect cancellation intent before starting a new reservation
        if _looks_like_cancellation(text):
            reservations = await reservation_service.find_active_by_customer(session, customer.id)
            if not reservations:
                return _res_prompt(reservation_prompts.NO_ACTIVE_RESERVATION, lang), None
            if len(reservations) == 1:
                res = reservations[0]
                buttons = _build_cancel_confirm_buttons(res.id)
                return _res_prompt(reservation_prompts.CANCEL_CONFIRM_PROMPT, lang), buttons
            # Multiple reservations → let the customer choose which to cancel
            await draft_store.put_chat_state(
                customer.id, {"waiting_for": "reservation_select_for_cancel"}
            )
            buttons = _build_reservation_select_buttons(reservations)
            return _res_prompt(reservation_prompts.SELECT_RESERVATION_CANCEL, lang), buttons

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
            # If input looks like a phone number (≥6 digits, no letters), reprompt
            digits_only = name.replace(" ", "").replace("+", "").replace("-", "")
            if digits_only.isdigit() and len(digits_only) >= 6:
                if lang in (Language.AR_LB, Language.ARABIZI):
                    return "يبدو أنك أدخلت رقم هاتف 😊 ما اسمك للحجز؟", None
                return "That looks like a phone number 😊 What's the name for the reservation?", None
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
            pending_res = await reservation_service.get_by_id(session, UUID(res_id_str))
            if pending_res is not None:
                return await _handle_modification_intent(
                    session, customer, text, lang, llm, pending_res
                )
        await draft_store.put_chat_state(customer.id, {"waiting_for": ""})
        return _res_prompt(reservation_prompts.DATE, lang), None

    # ── Modification: re-send selection buttons when user types (T035) ────────
    if waiting_for == "reservation_select_for_modify":
        reservations = await reservation_service.find_active_by_customer(session, customer.id)
        if not reservations:
            return _res_prompt(reservation_prompts.NO_ACTIVE_RESERVATION, lang), None
        buttons = _build_reservation_select_buttons(reservations)
        return _res_prompt(reservation_prompts.SELECT_RESERVATION_MODIFY, lang), buttons

    # ── Cancellation: re-send selection buttons when user types (T040) ────────
    if waiting_for == "reservation_select_for_cancel":
        reservations = await reservation_service.find_active_by_customer(session, customer.id)
        if not reservations:
            return _res_prompt(reservation_prompts.NO_ACTIVE_RESERVATION, lang), None
        buttons = _build_reservation_select_buttons(reservations)
        return _res_prompt(reservation_prompts.SELECT_RESERVATION_CANCEL, lang), buttons

    # ── Unknown state — restart ───────────────────────────────────────────────
    await reservation_draft_service.start_draft(customer.id, lang)
    await draft_store.put_chat_state(customer.id, {"waiting_for": ""})
    return _res_prompt(reservation_prompts.DATE, lang), None


# ── Modification helpers ──────────────────────────────────────────────────────


_TIME_PATTERNS = frozenset({
    "am", "pm", "a.m", "p.m", "noon", "midnight",
    "morning", "evening", "night", "afternoon",
    "صباح", "مساء", "ظهر", "ليل",
    "masa", "sbeh", "leil",
})

_DATE_PATTERNS = frozenset({
    "today", "tomorrow", "yesterday", "sunday", "monday", "tuesday",
    "wednesday", "thursday", "friday", "saturday",
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
    "اليوم", "بكرا", "بكره", "الأحد", "الاثنين", "الثلاثاء",
    "الأربعاء", "الخميس", "الجمعة", "السبت",
    "bukra", "lyom", "nhar",
})


def _has_digits(text: str) -> bool:
    return any(c.isdigit() for c in text)


def _input_matches_field(text: str, waiting_for: str) -> bool:
    """Return True when the user's input is plausibly an answer for waiting_for.

    Fields that accept button-driven input (seating, select, modify, cancel)
    always return True so text fallback re-sends the buttons instead of
    breaking the flow.
    """
    # Button-driven steps and open-ended states always pass through
    _OPEN_STATES = {
        "reservation_seating_indoor_outdoor",
        "reservation_seating_smoking",
        "reservation_seating_terrace",
        "reservation_seating_reask",
        "reservation_modify_seating",
        "reservation_modify_pending",
        "reservation_select_for_modify",
        "reservation_select_for_cancel",
        "reservation_date_confirm",
    }
    if waiting_for in _OPEN_STATES:
        return True

    lower = text.strip().lower()

    if waiting_for == "reservation_time":
        return _has_digits(lower) or any(kw in lower for kw in _TIME_PATTERNS)

    if waiting_for == "reservation_date":
        return _has_digits(lower) or any(kw in lower for kw in _DATE_PATTERNS)

    if waiting_for == "reservation_party_size":
        number_words = {
            "one", "two", "three", "four", "five", "six", "seven", "eight",
            "nine", "ten", "eleven", "twelve",
            "واحد", "اثنين", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة",
        }
        return _has_digits(lower) or any(w in lower for w in number_words)

    if waiting_for == "reservation_name":
        return bool(lower)  # accept any non-empty input, including digit strings

    if waiting_for == "reservation_phone":
        return _has_digits(lower)

    # Default: pass through for any unrecognised reservation_* state
    return True


def _looks_like_modification(text: str) -> bool:
    """Quick keyword scan to route modification intents before an LLM call. T037."""
    lower = text.lower()
    return any(kw in lower for kw in _MODIFICATION_KEYWORDS)


def _looks_like_cancellation(text: str) -> bool:
    """Quick keyword scan to route cancellation intents before an LLM call. T040."""
    lower = text.lower()
    return any(kw in lower for kw in _CANCELLATION_KEYWORDS)


def _build_cancel_confirm_buttons(reservation_id: UUID) -> list[dict[str, str]]:
    """Build yes/no confirmation buttons for a cancellation request. T040, FR-017."""
    return [
        {"label": "❌ Yes, cancel it", "callback_data": f"res_cancel_confirm:{reservation_id}"},
        {"label": "↩️ No, keep it", "callback_data": f"res_cancel_abort:{reservation_id}"},
    ]


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


async def begin_cancellation(
    session: AsyncSession,
    customer: Customer,
    reservation_id: UUID,
    chat_id: int,
    messenger: MessengerClient,
) -> None:
    """Public. Called from router after res_select: in cancel context. T041, FR-017."""
    res = await reservation_service.get_by_id(session, reservation_id)
    if res is None:
        await messenger.send_message(
            chat_id=chat_id,
            text="Sorry, that reservation could not be found.",
        )
        return
    lang = res.language
    buttons = _build_cancel_confirm_buttons(reservation_id)
    await messenger.send_message(
        chat_id=chat_id,
        text=_res_prompt(reservation_prompts.CANCEL_CONFIRM_PROMPT, lang),
        buttons=buttons,
    )
    await draft_store.put_chat_state(customer.id, {"waiting_for": ""})
