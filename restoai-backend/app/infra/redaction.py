"""PII redaction — single source of truth for all log writes and LLM prompts.

Covers Lebanese phone formats, customer display names, and free-form addresses.
Every log formatter and every LLM/embedding adapter MUST route its text through
this module before emission. Bypassing requires a documented exception in
DECISIONS.md (constitution Principle V).
"""
import re
from typing import Any

# ── phone patterns ────────────────────────────────────────────────────────────
#
# Lebanese formats in scope (from spec FR-012 and data-model.md):
#   International : +961 X XXX XXX  or  +961XX XXXXXX
#   Local prefix  : 03, 70, 71, 76, 78, 79, 81
#   Separators    : space, hyphen, or none

_PHONE_PATTERNS: list[re.Pattern[str]] = [
    # +961 followed by 7–9 significant digits, optional separators
    re.compile(r"\+961[\s-]?\d{1,2}[\s-]?\d{3}[\s-]?\d{3,4}"),
    # Local 8-digit with explicit prefix: 03/70/71/76/78/79/81 + 6 digits
    # with space/hyphen separators (e.g. "03 123 456", "70 123 456")
    re.compile(r"\b(03|7[016789]|81)[\s-]?\d{3}[\s-]?\d{3}\b"),
    # Compact local — no separators (e.g. "03123456", "70123456")
    re.compile(r"\b(?:03|70|71|76|78|79|81)\d{6}\b"),
]

_PHONE_TOKEN = "[PHONE_REDACTED]"  # noqa: S105
_NAME_TOKEN = "[NAME_REDACTED]"  # noqa: S105
_ADDRESS_TOKEN = "[ADDRESS_REDACTED]"  # noqa: S105


def redact(text: str) -> str:
    """Replace detectable phone-number PII in a text string with redaction tokens.

    Safe to call on arbitrary log strings. Non-phone content is unchanged.
    """
    for pattern in _PHONE_PATTERNS:
        text = pattern.sub(_PHONE_TOKEN, text)
    return text


def redact_name(name: str) -> str:  # noqa: ARG001
    """Return a name redaction token. Use for display_name fields in logs."""
    return _NAME_TOKEN


def redact_address(address: str) -> str:  # noqa: ARG001
    """Return an address redaction token. Use for text_value/lat/lon in logs."""
    return _ADDRESS_TOKEN


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Shallow-copy a dict and apply redact() to every string value."""
    return {k: redact(v) if isinstance(v, str) else v for k, v in data.items()}
