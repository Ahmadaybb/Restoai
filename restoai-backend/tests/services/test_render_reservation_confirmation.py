"""T015 — render_reservation_confirmation: synthesis tier + fallback.

Tests: (a) confirmation text contains reference number; (b) is_modification=True
changes the fallback prefix; (c) LLM error falls back to plain-text summary
without raising. Constitution Principle II.
"""
from __future__ import annotations

import datetime as _dt
from uuid import uuid4

import pytest

from app.domain.language import Language
from app.domain.reservation import Reservation, ReservationState, SeatingPreference
from app.domain.tools import RenderReservationConfirmationIn
from app.services.tools.render_reservation_confirmation import (
    render_reservation_confirmation,
)

# ── helpers ───────────────────────────────────────────────────────────────────

def _sample_reservation(reference: str = "RES1234567") -> Reservation:
    return Reservation(
        id=uuid4(),
        reference=reference,
        customer_id=uuid4(),
        date=_dt.date(2026, 7, 15),
        time=_dt.time(19, 30),
        party_size=4,
        name="Alice",
        phone="+96171234567",
        seating_preference=SeatingPreference.INDOOR_NON_SMOKING,
        state=ReservationState.ACTIVE,
        language=Language.EN,
    )


# ── fake clients ──────────────────────────────────────────────────────────────

class _FakeSynthesisClient:
    """Returns a canned response that echoes the user message content."""

    def __init__(self, response: str = "") -> None:
        self._response = response
        self.synthesis_calls: list[dict[str, str]] = []

    async def complete_synthesis(
        self, *, system: str, user: str, **_: object
    ) -> str:
        self.synthesis_calls.append({"system": system, "user": user})
        return self._response or f"Confirmed! {user}"

    async def complete_mechanical(
        self, *, system: str, user: str, **_: object
    ) -> str:
        raise AssertionError("synthesis tool must not call complete_mechanical")


class _BrokenSynthesisClient:
    async def complete_synthesis(
        self, *, system: str, user: str, **_: object
    ) -> str:
        raise RuntimeError("groq_unavailable")

    async def complete_mechanical(
        self, *, system: str, user: str, **_: object
    ) -> str:
        raise AssertionError("synthesis tool must not call complete_mechanical")


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirmation_text_contains_reference() -> None:
    ref = "RES9ABCDEF"
    reservation = _sample_reservation(ref)
    client = _FakeSynthesisClient(f"Your reservation {ref} is confirmed!")
    inp = RenderReservationConfirmationIn(reservation=reservation, language=Language.EN)

    result = await render_reservation_confirmation(inp, client)

    assert ref in result.text


@pytest.mark.asyncio
async def test_is_modification_true_sends_modification_mode_to_llm() -> None:
    reservation = _sample_reservation()
    client = _FakeSynthesisClient("Updated your reservation!")
    inp = RenderReservationConfirmationIn(
        reservation=reservation, language=Language.EN, is_modification=True
    )

    await render_reservation_confirmation(inp, client)

    assert client.synthesis_calls, "synthesis was not called"
    user_msg = client.synthesis_calls[0]["user"]
    assert "MODIFICATION" in user_msg


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_plain_text_with_reference() -> None:
    ref = "RES5FALLBK"
    reservation = _sample_reservation(ref)
    client = _BrokenSynthesisClient()
    inp = RenderReservationConfirmationIn(reservation=reservation, language=Language.EN)

    result = await render_reservation_confirmation(inp, client)

    assert ref in result.text
    assert "confirmed" in result.text.lower()


@pytest.mark.asyncio
async def test_llm_failure_modification_fallback_says_updated() -> None:
    reservation = _sample_reservation()
    client = _BrokenSynthesisClient()
    inp = RenderReservationConfirmationIn(
        reservation=reservation, language=Language.EN, is_modification=True
    )

    result = await render_reservation_confirmation(inp, client)

    assert "updated" in result.text.lower()


@pytest.mark.asyncio
async def test_synthesis_tier_only_mechanical_never_called() -> None:
    reservation = _sample_reservation()
    client = _FakeSynthesisClient("Confirmed!")
    inp = RenderReservationConfirmationIn(reservation=reservation, language=Language.EN)

    await render_reservation_confirmation(inp, client)

    assert len(client.synthesis_calls) == 1
