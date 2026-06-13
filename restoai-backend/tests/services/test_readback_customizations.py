"""T083: render_readback places customizations under their parent items.

Three customization kinds across two items:
  - Hummus: remove("no garlic"), add("extra tahini")
  - Fattoush: cook_pref("dressing on the side")

Each must appear under its parent in both the LLM prompt and the fallback
plain-text path. FR-016.
"""
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from app.domain.language import Language
from app.domain.menu import MenuItem
from app.domain.order import Customization, OrderDraft, OrderItem
from app.domain.tools import RenderReadbackIn

# ── Shared data ────────────────────────────────────────────────────────────────

_HUMMUS = MenuItem(
    id="cold_mezza_hummus",
    category="COLD MEZZA",
    name_en="Hummus",
    name_ar="حمص",
    price_usd=Decimal("7.00"),
)

_FATTOUSH = MenuItem(
    id="salad_fattoush",
    category="SALADS",
    name_en="Fattoush",
    name_ar="فتوش",
    price_usd=Decimal("6.00"),
)


def _draft() -> OrderDraft:
    return OrderDraft(
        id=uuid4(),
        customer_id=uuid4(),
        items=[
            OrderItem(
                menu_item_id="cold_mezza_hummus",
                quantity=1,
                customizations=[
                    Customization(kind="remove", text="no garlic"),
                    Customization(kind="add", text="extra tahini"),
                ],
            ),
            OrderItem(
                menu_item_id="salad_fattoush",
                quantity=2,
                customizations=[
                    Customization(kind="cook_pref", text="dressing on the side"),
                ],
            ),
        ],
        fulfillment="delivery",
        language=Language.EN,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )


def _get_item_mock(item_id: str) -> MenuItem | None:
    return {"cold_mezza_hummus": _HUMMUS, "salad_fattoush": _FATTOUSH}.get(item_id)


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_customizations_appear_in_llm_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All customizations from both items must appear in the synthesis LLM prompt."""
    from app.services.tools import render_readback as tool

    monkeypatch.setattr("app.repositories.menu_repo.get_item", _get_item_mock)

    captured_prompt: list[str] = []

    class _FakeLLM:
        async def complete_synthesis(self, *, system: str, user: str, **kw: Any) -> str:
            captured_prompt.append(user)
            return "Your order is confirmed."

        async def complete_mechanical(self, *, system: str, user: str, **kw: Any) -> str:
            raise AssertionError("mechanical must not be called in render_readback")

    await tool.render_readback(
        RenderReadbackIn(draft=_draft(), language=Language.EN),
        llm=_FakeLLM(),
    )

    assert len(captured_prompt) == 1
    prompt = captured_prompt[0]

    # All three customization texts must reach the LLM
    assert "no garlic" in prompt
    assert "extra tahini" in prompt
    assert "dressing on the side" in prompt

    # Both item names must appear
    assert "Hummus" in prompt
    assert "Fattoush" in prompt


@pytest.mark.asyncio
async def test_customizations_in_fallback_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the LLM fails, the raw fallback text still includes all customizations."""
    from app.services.tools import render_readback as tool

    monkeypatch.setattr("app.repositories.menu_repo.get_item", _get_item_mock)

    class _FailingLLM:
        async def complete_synthesis(self, *, system: str, user: str, **kw: Any) -> str:
            raise RuntimeError("LLM unavailable")

        async def complete_mechanical(self, *, system: str, user: str, **kw: Any) -> str:
            raise AssertionError("mechanical not used")

    result = await tool.render_readback(
        RenderReadbackIn(draft=_draft(), language=Language.EN),
        llm=_FailingLLM(),
    )

    assert "no garlic" in result.text
    assert "extra tahini" in result.text
    assert "dressing on the side" in result.text
    # Confirm/Edit buttons still present on fallback path
    assert any("confirm" in b.callback_data for b in result.buttons)
    assert any("edit" in b.callback_data for b in result.buttons)


@pytest.mark.asyncio
async def test_each_customization_under_correct_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hummus customizations appear before Fattoush customization in the text."""
    from app.services.tools import render_readback as tool

    monkeypatch.setattr("app.repositories.menu_repo.get_item", _get_item_mock)

    class _FailingLLM:
        async def complete_synthesis(self, *, system: str, user: str, **kw: Any) -> str:
            raise RuntimeError("LLM unavailable")

        async def complete_mechanical(self, *, system: str, user: str, **kw: Any) -> str:
            raise AssertionError("not called")

    result = await tool.render_readback(
        RenderReadbackIn(draft=_draft(), language=Language.EN),
        llm=_FailingLLM(),
    )

    text = result.text
    hummus_pos = text.index("Hummus")
    fattoush_pos = text.index("Fattoush")
    no_garlic_pos = text.index("no garlic")
    dressing_pos = text.index("dressing on the side")

    # Hummus customizations must appear between the Hummus and Fattoush lines
    assert hummus_pos < no_garlic_pos < fattoush_pos, (
        "Hummus customizations must appear under Hummus and before Fattoush"
    )
    # Fattoush customization must appear after the Fattoush line
    assert dressing_pos > fattoush_pos, (
        "Fattoush customization must appear after the Fattoush item line"
    )
