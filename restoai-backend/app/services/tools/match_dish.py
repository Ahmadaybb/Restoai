"""match_dish tool — FR-005.

Second-pass resolver for ambiguous item phrases. Uses the in-memory fuzzy
index first; calls the mechanical LLM only when the fuzzy lookup is
inconclusive (score < CONFIRM_THRESHOLD).
"""
import json
import logging
from typing import Any

from app.domain.clients import LLMClient
from app.domain.tools import DishAlternative, MatchDishIn, MatchDishOut
from app.repositories import menu_repo

logger = logging.getLogger(__name__)

_MATCH_THRESHOLD = 55
_CONFIRM_THRESHOLD = 75

_SYSTEM = """\
You are a dish-matching assistant for a Lebanese restaurant.

Given an ambiguous item phrase and a list of candidate menu items, return
the BEST match or null if none fits.

Respond ONLY with valid JSON:
{"menu_item_id": "..." | null, "score": 0.0-1.0}
"""


async def match_dish(inp: MatchDishIn, llm: LLMClient) -> MatchDishOut:
    candidates = menu_repo.find_by_phrase(inp.phrase)

    if not candidates:
        return MatchDishOut(menu_item_id=None, score=0.0, alternatives=[])

    from rapidfuzz import fuzz

    scored = []
    for item in candidates:
        search_text = f"{item.name_en} {item.name_ar or ''}"
        score = fuzz.token_set_ratio(inp.phrase.lower(), search_text.lower()) / 100.0
        scored.append((item, score))
    scored.sort(key=lambda x: x[1], reverse=True)

    best_item, best_score = scored[0]

    if best_score >= _CONFIRM_THRESHOLD / 100.0:
        alternatives = [
            DishAlternative(menu_item_id=item.id, score=round(s, 2))
            for item, s in scored[1:3]
            if s > _MATCH_THRESHOLD / 100.0
        ]
        return MatchDishOut(
            menu_item_id=best_item.id,
            score=round(best_score, 2),
            alternatives=alternatives,
        )

    # Score is in the grey zone — ask the cheap LLM
    candidate_list = [
        {"id": item.id, "name_en": item.name_en, "name_ar": item.name_ar}
        for item, _ in scored[:5]
    ]
    try:
        raw = await llm.complete_mechanical(
            system=_SYSTEM,
            user=json.dumps(
                {"phrase": inp.phrase, "candidates": candidate_list}, ensure_ascii=False
            ),
            response_format=dict,
        )
        data: dict[str, Any] = json.loads(raw)
        item_id: str | None = data.get("menu_item_id")
        llm_score = float(data.get("score", best_score))
        if item_id and menu_repo.get_item(item_id):
            return MatchDishOut(
                menu_item_id=item_id,
                score=round(llm_score, 2),
                alternatives=[],
            )
    except Exception:
        logger.warning("match_dish_llm_failed", extra={"phrase": inp.phrase})

    if best_score >= _MATCH_THRESHOLD / 100.0:
        return MatchDishOut(
            menu_item_id=best_item.id,
            score=round(best_score, 2),
            alternatives=[
                DishAlternative(menu_item_id=item.id, score=round(s, 2))
                for item, s in scored[1:3]
                if s > 0
            ],
        )
    return MatchDishOut(menu_item_id=None, score=round(best_score, 2), alternatives=[])
