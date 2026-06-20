"""parse_order tool — FR-003, FR-005, FR-006.

Two-step resolution:
1. Mechanical-tier LLM extracts item phrases + quantities from free text.
   The full menu name list is injected so the LLM recognises multi-word
   dish names ("Meat Rice", "Signature Sfiha Dozen") as single units.
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

_SYSTEM_TEMPLATE = """\
You are an order parsing assistant for a Lebanese restaurant chatbot.

== MENU ITEMS (complete list — use these names as the source of truth) ==
{menu_names}

Extract ordered items from the customer's message. Each item has:
- action: "add" (default) or "remove" (when customer says remove/take off/don't want)
- phrase: the dish name, matched as closely as possible to a name from the menu list above
- quantity: integer >= 1 (default 1 if not stated)
  IMPORTANT: "Dozen" in names like "Signature Sfiha Dozen" is part of the product name, NOT a quantity multiplier.
  "a dozen sfiha" or "dozen sfiha" → action=add, phrase="Signature Sfiha Dozen", quantity=1
- customizations: list of modifications (kind: "add"|"remove"|"cook_pref"|"extra_side"|"other", text: full phrase)

RULES:
- Multi-word menu names like "Meat Rice", "Mixed Raw Meat Plate", "Chicken Wings Provencal" are SINGLE items — never split them
- "phrase" must be the complete dish name — match the closest entry from the menu list above
- Global modifiers like "without oil" or "no salt" apply to ALL items as a customization on each
- Each dish appears ONCE in the items list — never duplicate the same dish
- Do NOT create an item entry for modifier phrases like "without oil"
- Use action "remove" when customer says "remove", "take off", "cancel", "I don't want", "without", "not [item]", "instead of [item]", "no [item]", "not the [item]"
- Use action "add" for all normal order requests (default)
- "not hummus har, the name hummus only" → remove hummus har, add hummus
- PRONOUNS: Words like "it", "that", "this", "them", "those" are NOT menu item names — never substitute a pronoun with a guessed dish name. If the message says "I want it" and "it" has no named dish referent in the SAME message, use phrase="it" literally so it can be resolved from context. Never invent a dish for a pronoun.

Respond ONLY with valid JSON:
{{"items": [{{"action": "add", "phrase": "...", "quantity": 1, "customizations": [{{"kind": "...", "text": "..."}}]}}]}}

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
    if any(w in t for w in ["side ", "fries", "salad"]):
        return "extra_side"
    return "other"


async def parse_order(inp: ParseOrderIn, llm: LLMClient) -> ParseOrderOut:
    all_menu_items = menu_repo.get_menu()
    menu_names = "\n".join(sorted(set(item.name_en for item in all_menu_items if item.name_en)))
    system = _SYSTEM_TEMPLATE.format(menu_names=menu_names)

    try:
        raw = await llm.complete_mechanical(
            system=system,
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
    remove_phrases: list[str] = []
    unresolved: list[str] = []
    match_scores: list[float] = []

    for raw_item in raw_items:
        action: str = raw_item.get("action", "add")
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

        if action == "remove":
            remove_phrases.append(phrase)
            continue

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
    return ParseOrderOut(
        items=resolved,
        remove_phrases=remove_phrases,
        unresolved=unresolved,
        confidence=round(confidence, 2),
    )
