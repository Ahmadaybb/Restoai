"""T014 — extract_reservation_fields: tier discipline + graceful failure.

Tests: (a) valid extraction; (b) informal date flag; (c) JSON parse error
returns all-None; (d) mechanical tier only — synthesis never called.
Constitution Principle II.
"""
from __future__ import annotations

import json

import pytest

from app.domain.language import Language
from app.domain.tools import ExtractReservationFieldsIn
from app.services.tools.extract_reservation_fields import extract_reservation_fields

# ── fake clients ──────────────────────────────────────────────────────────────

class _FakeLLMClient:
    """Records calls; raises if synthesis is invoked (tier discipline)."""

    def __init__(self, mechanical_response: str) -> None:
        self._response = mechanical_response
        self.mechanical_call_count = 0
        self.synthesis_call_count = 0

    async def complete_mechanical(
        self, *, system: str, user: str, **_: object
    ) -> str:
        self.mechanical_call_count += 1
        return self._response

    async def complete_synthesis(
        self, *, system: str, user: str, **_: object
    ) -> str:
        self.synthesis_call_count += 1
        raise AssertionError(
            "extract_reservation_fields must not call complete_synthesis"
        )


class _BrokenLLMClient:
    """Always raises on complete_mechanical to test graceful fallback."""

    async def complete_mechanical(self, *, system: str, user: str, **_: object) -> str:
        raise RuntimeError("groq_unavailable")

    async def complete_synthesis(self, *, system: str, user: str, **_: object) -> str:
        raise AssertionError("synthesis must not be called")


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_extraction_returns_all_fields() -> None:
    payload = {
        "date": "2026-07-15",
        "time": "19:30",
        "party_size": 4,
        "name": "Alice Khoury",
        "phone": "+96171234567",
        "date_is_informal": False,
    }
    client = _FakeLLMClient(json.dumps(payload))
    inp = ExtractReservationFieldsIn(
        text="Table for 4 on July 15 at 7:30pm, name Alice Khoury +96171234567",
        language=Language.EN,
    )
    result = await extract_reservation_fields(inp, client)

    assert result.party_size == 4
    assert result.name == "Alice Khoury"
    assert result.phone == "+96171234567"
    assert result.date_is_informal is False
    assert str(result.date) == "2026-07-15"


@pytest.mark.asyncio
async def test_informal_date_sets_flag() -> None:
    payload = {
        "date": "2026-06-20",
        "time": "20:00",
        "party_size": 2,
        "name": None,
        "phone": None,
        "date_is_informal": True,
    }
    client = _FakeLLMClient(json.dumps(payload))
    inp = ExtractReservationFieldsIn(
        text="Table for 2 next Friday at 8pm", language=Language.EN
    )
    result = await extract_reservation_fields(inp, client)

    assert result.date_is_informal is True
    assert result.party_size == 2


@pytest.mark.asyncio
async def test_json_parse_error_returns_all_none() -> None:
    client = _FakeLLMClient("not valid json {{ broken")
    inp = ExtractReservationFieldsIn(text="book a table", language=Language.EN)
    result = await extract_reservation_fields(inp, client)

    assert result.date is None
    assert result.time is None
    assert result.party_size is None
    assert result.name is None
    assert result.phone is None
    assert result.date_is_informal is False


@pytest.mark.asyncio
async def test_llm_error_returns_all_none() -> None:
    client = _BrokenLLMClient()
    inp = ExtractReservationFieldsIn(text="book a table", language=Language.EN)
    result = await extract_reservation_fields(inp, client)

    assert result.date is None
    assert result.party_size is None


@pytest.mark.asyncio
async def test_mechanical_tier_only_synthesis_never_called() -> None:
    payload = {
        "date": None,
        "time": None,
        "party_size": None,
        "name": None,
        "phone": None,
        "date_is_informal": False,
    }
    client = _FakeLLMClient(json.dumps(payload))
    inp = ExtractReservationFieldsIn(text="I want to reserve", language=Language.EN)
    await extract_reservation_fields(inp, client)

    assert client.mechanical_call_count == 1
    assert client.synthesis_call_count == 0
