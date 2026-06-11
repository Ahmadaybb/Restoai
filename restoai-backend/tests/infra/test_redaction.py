"""T021 — PII redaction utility covers Lebanese phone formats.

Constitution Principle V; data-model.md §PII redaction.
"""
import pytest

from app.infra.redaction import redact, redact_address, redact_name


@pytest.mark.parametrize(
    "raw",
    [
        # International format
        "+961 3 123 456",
        "+9613123456",
        "+961 70 123 456",
        "+96170123456",
        # Local 03 prefix
        "03 123 456",
        "03123456",
        "03-123-456",
        # Local 70/71/76/78/79/81 prefixes
        "70 123 456",
        "70123456",
        "71 123 456",
        "71123456",
        "76 123 456",
        "78 123 456",
        "79 123 456",
        "81 123 456",
        "81123456",
    ],
)
def test_phone_is_redacted(raw: str) -> None:
    result = redact(f"Reach me at {raw} anytime")
    # The raw digits must not appear verbatim
    assert raw not in result
    assert "[PHONE_REDACTED]" in result


def test_normal_text_unchanged() -> None:
    text = "Please send 2 hummus and 1 fattoush."
    assert redact(text) == text


def test_multiple_phones_in_one_string() -> None:
    text = "Call +9613123456 or 70123456 for more info."
    result = redact(text)
    assert "+9613123456" not in result
    assert "70123456" not in result
    assert result.count("[PHONE_REDACTED]") == 2


def test_redact_name_returns_token() -> None:
    assert redact_name("Ahmad Ayoub") == "[NAME_REDACTED]"
    assert redact_name("") == "[NAME_REDACTED]"


def test_redact_address_returns_token() -> None:
    assert redact_address("Hamra Street near AUB") == "[ADDRESS_REDACTED]"
