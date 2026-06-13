"""extract_reservation_fields tool — FR-002, FR-009, research.md R11.

Mechanical-tier LLM extracts date, time, party_size, name, phone from
free text. On JSON parse failure returns all-None rather than raising.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
from functools import lru_cache
from pathlib import Path

from app.domain.clients import LLMClient
from app.domain.language import Language
from app.domain.tools import ExtractedReservationFields, ExtractReservationFieldsIn

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


@lru_cache(maxsize=4)
def _load_system_prompt(lang_dir: str) -> str:
    path = _PROMPTS_DIR / lang_dir / "extract_reservation_fields.txt"
    return path.read_text(encoding="utf-8")


def _system_for(language: Language) -> str:
    lang_dir = "ar_lb" if language in (Language.AR_LB, Language.ARABIZI) else "en"
    return _load_system_prompt(lang_dir)


async def extract_reservation_fields(
    inp: ExtractReservationFieldsIn,
    llm: LLMClient,
) -> ExtractedReservationFields:
    system = _system_for(inp.language)
    today = _dt.datetime.utcnow().date().isoformat()
    user = f"Today's date: {today}\nLanguage: {inp.language}\nMessage: {inp.text[:1000]}"

    try:
        raw = await llm.complete_mechanical(
            system=system,
            user=user,
            response_format=dict,
        )
        data: dict[str, object] = json.loads(raw)
        return ExtractedReservationFields.model_validate(data)
    except Exception:
        logger.warning("extract_reservation_fields_failed")
        return ExtractedReservationFields()
