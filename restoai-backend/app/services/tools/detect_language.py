"""detect_language tool — FR-028.

Fast script/n-gram heuristic first; mechanical-tier LLM only on ambiguity
(confidence < 0.6) to keep cost low (Principle IV).
"""
import json
import logging

from app.domain.clients import LLMClient
from app.domain.language import Language
from app.domain.tools import DetectLanguageIn, DetectLanguageOut
from app.services.language_service import detect as heuristic_detect

logger = logging.getLogger(__name__)

_AMBIGUITY_THRESHOLD = 0.6

_SYSTEM = (
    "You are a language classifier for a Lebanese restaurant chatbot. "
    "Classify the customer message language as one of: en, ar_lb, arabizi. "
    "ar_lb = Lebanese Arabic written in Arabic script. "
    "arabizi = Lebanese Arabic written in Latin/digits (e.g. '3ala', 'habibi', 'shu'). "
    "en = English. "
    "Respond with ONLY a JSON object: "
    "{\"language\": \"en\"|\"ar_lb\"|\"arabizi\", \"confidence\": 0.0-1.0}"
)


async def detect_language(
    inp: DetectLanguageIn,
    llm: LLMClient | None = None,
) -> DetectLanguageOut:
    result = heuristic_detect(inp.text)

    if result.confidence >= _AMBIGUITY_THRESHOLD or llm is None:
        return DetectLanguageOut(
            language=result.language,
            confidence=result.confidence,
        )

    # Ambiguous — consult cheap-tier LLM
    try:
        raw = await llm.complete_mechanical(
            system=_SYSTEM,
            user=inp.text[:500],
            response_format=dict,
        )
        data = json.loads(raw)
        lang = Language(data.get("language", "en"))
        confidence = float(data.get("confidence", 0.7))
        return DetectLanguageOut(language=lang, confidence=confidence)
    except Exception:
        logger.warning("detect_language_llm_fallback_failed")
        return DetectLanguageOut(language=result.language, confidence=result.confidence)
