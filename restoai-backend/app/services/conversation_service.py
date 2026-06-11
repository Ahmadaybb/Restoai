"""ConversationService — orchestrates the full turn lifecycle.

Detect language → record Turn → classify intent → route to tool(s) →
render reply → record outbound Turn.

T051: parse_order → match_dish two-pass pipeline (FR-003, FR-005, FR-006).
T060: handle_text routing for US1 (order intent; query stub).
T062: on_start welcome flow (FR-001, FR-002).
T069: graceful degradation on ExternalDependencyError (FR-034).
"""
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clients import EmbeddingClient, LLMClient, MessengerClient
from app.domain.conversation import Turn
from app.domain.customer import Customer
from app.domain.errors import ExternalDependencyError
from app.domain.language import Intent, Language
from app.domain.order import OrderItem
from app.domain.tools import (
    AnswerMenuQuestionIn,
    MatchDishIn,
    ParseOrderIn,
    RenderReadbackIn,
)
from app.infra import draft_store
from app.infra.intent_classifier import classify
from app.infra.redaction import redact
from app.repositories import menu_repo, transcript_repo
from app.services import customer_service, order_draft_service
from app.services.language_service import detect as lang_detect
from app.services.language_service import reply_language
from app.services.tools import answer_menu_question as qa_tool
from app.services.tools import match_dish as match_dish_tool
from app.services.tools import parse_order as parse_order_tool
from app.services.tools import render_readback as readback_tool

logger = logging.getLogger(__name__)

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
    "👋 Welcome to {restaurant}! I'm your order assistant.\n\n"
    "Here's our menu:\n\n{menu}\n\n"
    "Just tell me what you'd like to order!"
)
_WELCOME_AR = (
    "👋 أهلاً بك في {restaurant}! أنا مساعدك للطلبات.\n\n"
    "إليك قائمة طعامنا:\n\n{menu}\n\n"
    "فقط أخبرني بما تريد طلبه!"
)

_FULFILLMENT_PROMPT_EN = "Would you like 🛵 Delivery or 🏪 Pickup?"
_FULFILLMENT_PROMPT_AR = "هل تريد التوصيل 🛵 أم الاستلام 🏪؟"

_ADDRESS_PROMPT_EN = "Please share your delivery address."
_ADDRESS_PROMPT_AR = "يرجى مشاركة عنوان التوصيل."

_QUERY_STUB_EN = "Menu Q&A is coming soon! For now, feel free to place an order."
_QUERY_STUB_AR = "الإجابة على أسئلة القائمة ستكون متاحة قريباً! للآن، يسعدنا استقبال طلبك."

RESTAURANT_NAME = "Lakkis Farm"


def _build_menu_text(language: Language) -> str:
    items = menu_repo.get_menu()
    by_category: dict[str, list[Any]] = {}
    for item in items:
        if not item.available:
            continue
        cat = item.category
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(item)

    lines = []
    for cat, cat_items in list(by_category.items())[:10]:
        lines.append(f"📌 {cat}")
        for item in cat_items[:8]:
            name = item.name_ar if language == Language.AR_LB else item.name_en
            lines.append(f"  • {name} — ${item.price_usd:.2f}")
    return "\n".join(lines)


async def on_start(
    session: AsyncSession,
    customer: Customer,
    telegram_chat_id: int,
    messenger: MessengerClient,
) -> None:
    """FR-001, FR-002: Send welcome + full menu on /start."""
    lang = Language.EN
    if customer.display_name:
        greeting = f"Welcome back, {customer.display_name}! 😊\n"
    else:
        greeting = ""

    menu_text = _build_menu_text(lang)
    template = _WELCOME_AR if lang == Language.AR_LB else _WELCOME_EN
    text = template.format(restaurant=RESTAURANT_NAME, menu=menu_text)
    if greeting:
        text = greeting + text

    await messenger.send_message(chat_id=telegram_chat_id, text=text)

    conv = await transcript_repo.get_or_create_conversation(session, customer.id)
    turn = Turn(
        conversation_id=conv.id,
        sender="bot",
        text=redact(text)[:4000],
        language=lang,
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

    # 3. Route intent
    reply_text: str
    buttons: list[dict[str, str]] | None = None

    try:
        if intent_result == Intent.ORDER:
            reply_text, buttons = await _handle_order_intent(
                session, customer, text, reply_lang, llm, conv.id
            )
        elif intent_result == Intent.QUERY:
            reply_text, buttons = await _handle_query_intent(
                session, text, reply_lang, llm, embedder
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

    # Check if fulfillment is set
    draft = await order_draft_service.get_draft(customer.id)
    if draft is None or draft.fulfillment is None:
        buttons = [
            {"label": "🛵 Delivery", "callback_data": "fulfillment:delivery"},
            {"label": "🏪 Pickup", "callback_data": "fulfillment:pickup"},
        ]
        if reply_lang == Language.AR_LB:
            return _FULFILLMENT_PROMPT_AR, buttons
        return _FULFILLMENT_PROMPT_EN, buttons

    # Has items + fulfillment — offer readback
    if draft.fulfillment == "delivery" and draft.address is None:
        if reply_lang == Language.AR_LB:
            return _ADDRESS_PROMPT_AR, None
        return _ADDRESS_PROMPT_EN, None

    # Ready for readback
    readback = await readback_tool.render_readback(
        RenderReadbackIn(draft=draft, language=reply_lang),
        llm=llm,
    )
    buttons = [b.model_dump() for b in readback.buttons]
    return readback.text, buttons
