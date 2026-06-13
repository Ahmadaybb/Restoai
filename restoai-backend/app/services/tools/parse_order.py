"""parse_order tool — FR-003, FR-005, FR-006.

Two-step resolution:
1. Mechanical-tier LLM extracts item phrases + quantities from free text.
2. For each phrase, in-memory fuzzy lookup via menu_repo.find_by_phrase().
   Unresolved phrases go to the unresolved list for second-pass match_dish.
"""
import json
import logging
from typing import Any

from app.domain.clients import LLMClient
from app.domain.order import Customization, OrderItem
from app.domain.tools import ParseOrderIn, ParseOrderOut
from app.repositories import menu_repo

logger = logging.getLogger(__name__)

_MATCH_THRESHOLD = 65

_SYSTEM = """\
You are an order parsing assistant for a Lebanese restaurant chatbot.

Extract ordered items from the customer's message. Each item has:
- phrase: ONLY the dish name (e.g. "fatoush", "hummus"). NEVER include modifiers in the phrase.
- quantity: integer >= 1 (default 1 if not stated). Formats like "1-fatoush" mean quantity 1.
- customizations: list of modifications that apply to this item.
  Each customization has:
  - kind: "add" | "remove" | "cook_pref" | "extra_side" | "other"
  - text: the FULL modification phrase with modifier word (e.g. "without oil", "extra spicy")

RULES:
- "phrase" must be the dish name only — never "fatoush without oil", only "fatoush"
- Global modifiers like "without oil" or "no salt" apply to ALL items as a customization on each
- Each dish appears ONCE in the items list — never duplicate the same dish
- Do NOT create an item entry for modifier phrases like "without oil"

Respond ONLY with valid JSON:
{"items": [{"phrase": "...", "quantity": 1, "customizations": [{"kind": "...", "text": "..."}]}]}

Only extract food items, not addresses, times, or other info.
"""


def _classify_custom_kind(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["no ", "without", "remove", "hold", "بدون"]):
        return "remove"
    if any(w in t for w in ["extra ", "add ", "more ", "with ", "زيادة"]):
        return "add"
    if any(w in t for w in ["well done", "medium", "rare", "spicy", "mild", "hot"]):
        return "cook_pref"
    if any(w in t for w in ["side ", "fries", "rice", "salad"]):
        return "extra_side"
    return "other"


async def parse_order(inp: ParseOrderIn, llm: LLMClient) -> ParseOrderOut:
    try:
        raw = await llm.complete_mechanical(
            system=_SYSTEM,
            user=f"Language: {inp.language}\nMessage: {inp.text[:1000]}",
            response_format=dict,
        )
        extracted: dict[str, Any] = json.loads(raw)
    except Exception:
        logger.warning("parse_order_llm_failed")
        return ParseOrderOut(items=[], unresolved=[inp.text], confidence=0.0)

    raw_items: list[dict[str, Any]] = extracted.get("items", [])
    if not raw_items:
        return ParseOrderOut(items=[], unresolved=[], confidence=1.0)

    resolved: list[OrderItem] = []
    unresolved: list[str] = []
    match_scores: list[float] = []

    for raw_item in raw_items:
        phrase: str = raw_item.get("phrase", "")
        quantity: int = max(1, int(raw_item.get("quantity", 1)))
        raw_customs: list[dict[str, Any]] = raw_item.get("customizations", [])

        customizations = [
            Customization(
                kind=c.get("kind", _classify_custom_kind(c.get("text", ""))),
                text=c.get("text", ""),
            )
            for c in raw_customs
            if c.get("text")
        ]

        matches = menu_repo.find_by_phrase(phrase)
        if matches:
            best = matches[0]
            resolved.append(
                OrderItem(
                    menu_item_id=best.id,
                    quantity=quantity,
                    customizations=customizations,
                )
            )
            match_scores.append(1.0)
        else:
            unresolved.append(phrase)
            match_scores.append(0.0)

    confidence = (
        sum(match_scores) / len(match_scores) if match_scores else 0.0
    )
    return ParseOrderOut(items=resolved, unresolved=unresolved, confidence=round(confidence, 2))
