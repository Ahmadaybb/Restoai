"""render_reservation_confirmation tool — FR-011, FR-016, research.md R11.

Synthesis-tier LLM renders a localized reservation confirmation message.
Falls back to a structured plain-text summary on LLM error.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from app.domain.clients import LLMClient
from app.domain.language import Language
from app.domain.tools import RenderReservationConfirmationIn, RenderReservationConfirmationOut

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

_SEATING_LABELS_EN = {
    "indoor_smoking": "Indoor — Smoking Area",
    "indoor_non_smoking": "Indoor — Non-Smoking Area",
    "outdoor_terrace": "Outdoor — Terrace",
    "outdoor_non_terrace": "Outdoor — Non-Terrace",
}

_SEATING_LABELS_AR = {
    "indoor_smoking": "داخلي — قسم التدخين",
    "indoor_non_smoking": "داخلي — قسم عدم التدخين",
    "outdoor_terrace": "خارجي — تراس",
    "outdoor_non_terrace": "خارجي — بدون تراس",
}


@lru_cache(maxsize=4)
def _load_system_prompt(lang_dir: str) -> str:
    path = _PROMPTS_DIR / lang_dir / "render_reservation_confirmation.txt"
    return path.read_text(encoding="utf-8")


def _system_for(language: Language) -> str:
    lang_dir = "ar_lb" if language in (Language.AR_LB, Language.ARABIZI) else "en"
    return _load_system_prompt(lang_dir)


def _labels_for(language: Language) -> dict[str, str]:
    if language in (Language.AR_LB, Language.ARABIZI):
        return _SEATING_LABELS_AR
    return _SEATING_LABELS_EN


def _build_user_message(inp: RenderReservationConfirmationIn) -> str:
    r = inp.reservation
    labels = _labels_for(inp.language)
    seating = labels.get(r.seating_preference.value, r.seating_preference.value)
    mode = "MODIFICATION CONFIRMATION" if inp.is_modification else "NEW RESERVATION CONFIRMATION"
    return (
        f"Mode: {mode}\n"
        f"Reference: {r.reference}\n"
        f"Date: {r.date}\n"
        f"Time: {r.time.strftime('%H:%M')}\n"
        f"Party size: {r.party_size}\n"
        f"Name: {r.name}\n"
        f"Phone: {r.phone}\n"
        f"Seating: {seating}"
    )


def _plain_text_fallback(inp: RenderReservationConfirmationIn) -> str:
    r = inp.reservation
    labels = _labels_for(inp.language)
    seating = labels.get(r.seating_preference.value, r.seating_preference.value)
    intro = "✅ Reservation updated!" if inp.is_modification else "✅ Reservation confirmed!"
    return (
        f"{intro}\n"
        f"📋 Ref: {r.reference}\n"
        f"📅 Date: {r.date}\n"
        f"🕐 Time: {r.time.strftime('%H:%M')}\n"
        f"👥 Party: {r.party_size}\n"
        f"👤 Name: {r.name}\n"
        f"📞 Phone: {r.phone}\n"
        f"🪑 Seating: {seating}"
    )


async def render_reservation_confirmation(
    inp: RenderReservationConfirmationIn,
    llm: LLMClient,
) -> RenderReservationConfirmationOut:
    system = _system_for(inp.language)
    user_msg = _build_user_message(inp)

    try:
        text = await llm.complete_synthesis(system=system, user=user_msg)
    except Exception:
        logger.warning("render_reservation_confirmation_llm_failed")
        text = _plain_text_fallback(inp)

    return RenderReservationConfirmationOut(text=text)
