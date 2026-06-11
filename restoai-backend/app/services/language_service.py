"""LanguageService — language detection and reply-language selection.

FR-028..FR-032: detect language of each customer turn; enforce that
Arabizi input always gets an English reply (FR-031).
"""
import re

from app.domain.language import DetectedLanguage, Language

# Arabic Unicode range: U+0600–U+06FF
_ARABIC_RE = re.compile(r"[؀-ۿ]")

# Common Arabizi digit-for-letter substitutions
_ARABIZI_MARKERS = re.compile(
    r"\b(?:3al|7al|2ahl|ma3|3ala|shu|habibi|yalla|keef|kifak|tfaddal|w2t)\b",
    re.IGNORECASE,
)

_ARABIZI_DIGITS = re.compile(r"\b\w*[23478]\w*\b")


def _detect_heuristic(text: str) -> tuple[Language, float]:
    arabic_chars = len(_ARABIC_RE.findall(text))
    total_chars = max(len(text.strip()), 1)
    arabic_ratio = arabic_chars / total_chars

    if arabic_ratio > 0.15:
        return Language.AR_LB, min(0.7 + arabic_ratio * 0.3, 0.99)

    arabizi_markers = len(_ARABIZI_MARKERS.findall(text))
    arabizi_digits = len(_ARABIZI_DIGITS.findall(text))
    arabizi_score = arabizi_markers * 0.3 + arabizi_digits * 0.1
    if arabizi_score > 0.3:
        return Language.ARABIZI, min(0.5 + arabizi_score, 0.85)

    return Language.EN, 0.9


def detect(text: str) -> DetectedLanguage:
    """Heuristic language detection — no LLM call."""
    lang, confidence = _detect_heuristic(text)
    return DetectedLanguage(language=lang, confidence=confidence)


def reply_language(detected: DetectedLanguage) -> Language:
    """FR-031: Arabizi input always gets an English reply."""
    if detected.language == Language.ARABIZI:
        return Language.EN
    return detected.language
