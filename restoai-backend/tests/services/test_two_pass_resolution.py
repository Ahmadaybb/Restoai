"""T052: Two-pass parse_order → match_dish pipeline tests.

Covers:
(a) parse_order alone resolves a clean order
(b) ambiguous phrase goes through match_dish and resolves with alternatives
(c) both fail → clarification prompt + counter increment
"""
import json
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.language import Language
from app.domain.menu import MenuItem
from app.domain.tools import (
    MatchDishIn,
    MatchDishOut,
    ParseOrderIn,
    ParseOrderOut,
)


class _FakeMechanicalLLM:
    def __init__(self, response: str) -> None:
        self._response = response

    async def complete_mechanical(self, *, system: str, user: str, **kwargs: Any) -> str:
        return self._response

    async def complete_synthesis(self, *, system: str, user: str, **kwargs: Any) -> str:
        raise AssertionError("synthesis must not be called in mechanical tools")


_HUMMUS = MenuItem(
    id="hummus",
    name_en="Hummus",
    name_ar="حمص",
    category="Dips",
    price_usd=Decimal("5.00"),
    available=True,
)
_FATTOUSH = MenuItem(
    id="fattoush",
    name_en="Fattoush",
    name_ar="فتوش",
    category="Salads",
    price_usd=Decimal("6.00"),
    available=True,
)

_CUSTOMER_ID = uuid4()


# ─────────────────────────────────────────────────────────────────────────────
# (a) parse_order alone resolves


@pytest.mark.asyncio
async def test_parse_order_resolves_clean_order(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.tools import parse_order as tool

    llm = _FakeMechanicalLLM(
        json.dumps({"items": [{"phrase": "hummus", "quantity": 2, "customizations": []}]})
    )
    monkeypatch.setattr("app.repositories.menu_repo.find_by_phrase", lambda _p: [_HUMMUS])

    result = await tool.parse_order(ParseOrderIn(text="2 hummus", language=Language.EN), llm=llm)

    assert len(result.items) == 1
    assert result.items[0].menu_item_id == "hummus"
    assert result.items[0].quantity == 2
    assert result.unresolved == []
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_parse_order_multiple_items_all_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.tools import parse_order as tool

    llm = _FakeMechanicalLLM(
        json.dumps({
            "items": [
                {"phrase": "hummus", "quantity": 1, "customizations": []},
                {"phrase": "fattoush", "quantity": 2, "customizations": []},
            ]
        })
    )

    def _find(phrase: str) -> list[MenuItem]:
        return [_HUMMUS] if "hummus" in phrase.lower() else [_FATTOUSH]

    monkeypatch.setattr("app.repositories.menu_repo.find_by_phrase", _find)

    result = await tool.parse_order(
        ParseOrderIn(text="1 hummus and 2 fattoush", language=Language.EN), llm=llm
    )

    assert len(result.items) == 2
    assert result.unresolved == []


# ─────────────────────────────────────────────────────────────────────────────
# (b) ambiguous phrase resolved by second-pass match_dish


@pytest.mark.asyncio
async def test_parse_order_unresolved_phrase_passed_to_match_dish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.tools import parse_order as tool

    llm = _FakeMechanicalLLM(
        json.dumps({"items": [{"phrase": "houmous", "quantity": 1, "customizations": []}]})
    )
    # First-pass fuzzy: no match → unresolved
    monkeypatch.setattr("app.repositories.menu_repo.find_by_phrase", lambda _p: [])

    result = await tool.parse_order(
        ParseOrderIn(text="1 houmous", language=Language.EN), llm=llm
    )

    assert result.items == []
    assert "houmous" in result.unresolved


@pytest.mark.asyncio
async def test_match_dish_resolves_ambiguous_phrase(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.tools import match_dish as tool

    llm = _FakeMechanicalLLM(json.dumps({"menu_item_id": "hummus", "score": 0.88}))
    monkeypatch.setattr("app.repositories.menu_repo.find_by_phrase", lambda _p: [_HUMMUS])
    monkeypatch.setattr("app.repositories.menu_repo.get_item", lambda _id: _HUMMUS)

    result = await tool.match_dish(
        MatchDishIn(phrase="houmous", language=Language.EN), llm=llm
    )

    assert result.menu_item_id == "hummus"
    assert result.score > 0.0


@pytest.mark.asyncio
async def test_two_pass_pipeline_in_conversation_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ambiguous phrase: parse_order fails → match_dish succeeds → item added."""
    from app.services import conversation_service

    # parse_order: one unresolved phrase
    mock_parse = AsyncMock(
        return_value=ParseOrderOut(items=[], unresolved=["houmous"], confidence=0.0)
    )
    # match_dish: resolves
    mock_match = AsyncMock(
        return_value=MatchDishOut(menu_item_id="hummus", score=0.9)
    )
    mock_add_items = AsyncMock(return_value=None)
    mock_get_draft = AsyncMock(return_value=None)
    mock_reset_fail = AsyncMock()
    mock_incr_fail = AsyncMock(return_value=1)

    session = AsyncMock()
    customer = _make_customer()
    fake_llm = _FakeMechanicalLLM("{}")

    monkeypatch.setattr("app.services.conversation_service.parse_order_tool", type("M", (), {"parse_order": mock_parse})())  # noqa: E501
    monkeypatch.setattr("app.services.conversation_service.match_dish_tool", type("M", (), {"match_dish": mock_match})())
    monkeypatch.setattr("app.services.conversation_service.order_draft_service", type("M", (), {
        "add_items": mock_add_items,
        "get_draft": mock_get_draft,
    })())
    monkeypatch.setattr("app.infra.draft_store.reset_failcount", mock_reset_fail)
    monkeypatch.setattr("app.infra.draft_store.incr_failcount", mock_incr_fail)

    result_text, buttons = await conversation_service._handle_order_intent(
        session=session,
        customer=customer,
        text="1 houmous",
        reply_lang=Language.EN,
        llm=fake_llm,
        conversation_id=uuid4(),
    )

    mock_match.assert_called_once()
    mock_add_items.assert_called_once()
    # After resolving, should ask for fulfillment (draft is None)
    assert "delivery" in result_text.lower() or "pickup" in result_text.lower() or buttons is not None


# ─────────────────────────────────────────────────────────────────────────────
# (c) both fail → clarification prompt + counter increment


@pytest.mark.asyncio
async def test_both_passes_fail_returns_clarification_and_increments_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import conversation_service

    mock_parse = AsyncMock(
        return_value=ParseOrderOut(items=[], unresolved=["xyzzy dish"], confidence=0.0)
    )
    mock_match = AsyncMock(
        return_value=MatchDishOut(menu_item_id=None, score=0.0)
    )
    mock_add_items = AsyncMock()
    mock_get_draft = AsyncMock(return_value=None)
    mock_reset_fail = AsyncMock()
    mock_incr_fail = AsyncMock(return_value=1)

    session = AsyncMock()
    customer = _make_customer()
    fake_llm = _FakeMechanicalLLM("{}")

    monkeypatch.setattr("app.services.conversation_service.parse_order_tool", type("M", (), {"parse_order": mock_parse})())
    monkeypatch.setattr("app.services.conversation_service.match_dish_tool", type("M", (), {"match_dish": mock_match})())
    monkeypatch.setattr("app.services.conversation_service.order_draft_service", type("M", (), {
        "add_items": mock_add_items,
        "get_draft": mock_get_draft,
    })())
    monkeypatch.setattr("app.infra.draft_store.reset_failcount", mock_reset_fail)
    monkeypatch.setattr("app.infra.draft_store.incr_failcount", mock_incr_fail)

    result_text, buttons = await conversation_service._handle_order_intent(
        session=session,
        customer=customer,
        text="1 xyzzy dish",
        reply_lang=Language.EN,
        llm=fake_llm,
        conversation_id=uuid4(),
    )

    # counter must be incremented for dish_match failure
    mock_incr_fail.assert_called()
    # add_items must NOT have been called (no items resolved)
    mock_add_items.assert_not_called()
    # reply must prompt for clarification
    assert "couldn't" in result_text.lower() or "find" in result_text.lower() or "rephrase" in result_text.lower()
    assert buttons is None


# ─────────────────────────────────────────────────────────────────────────────
# helpers


def _make_customer() -> Any:
    from app.domain.customer import Customer
    return Customer(id=_CUSTOMER_ID)
