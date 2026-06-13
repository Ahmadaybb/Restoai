"""T085: Unmappable customizations are NOT silently dropped.

When a customer attaches a customization that does not fit the standard kinds
(add / remove / cook_pref / extra_side), parse_order MUST preserve it as
kind="other" rather than omitting it. The bot then shows it in the read-back
so the customer can confirm or edit — it never disappears without the customer
knowing. FR-004; FR-006.
"""
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.conversation import Conversation
from app.domain.customer import Customer
from app.domain.language import Intent, Language
from app.domain.menu import MenuItem
from app.domain.order import Customization, OrderItem
from app.domain.tools import ParseOrderIn, ParseOrderOut

_HUMMUS = MenuItem(
    id="cold_mezza_hummus",
    category="COLD MEZZA",
    name_en="Hummus",
    name_ar="حمص",
    price_usd=Decimal("7.00"),
)

_CUSTOMER_ID = uuid4()


class _FakeMechanicalLLM:
    def __init__(self, response: str) -> None:
        self._response = response

    async def complete_mechanical(self, *, system: str, user: str, **kw: Any) -> str:
        return self._response

    async def complete_synthesis(self, *, system: str, user: str, **kw: Any) -> str:
        raise AssertionError("synthesis must not be called in parse_order")


class _FakeMessenger:
    async def send_message(self, *, chat_id: int, text: str, buttons: Any = None) -> None:
        pass


# ── Tests: parse_order tool behaviour ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_unmappable_customization_preserved_as_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A customization the LLM assigns kind='other' is NOT dropped."""
    from app.services.tools import parse_order as tool

    llm = _FakeMechanicalLLM(json.dumps({
        "items": [{
            "phrase": "hummus",
            "quantity": 1,
            "customizations": [{"kind": "other", "text": "serve it with extra love"}],
        }]
    }))
    monkeypatch.setattr("app.repositories.menu_repo.find_by_phrase", lambda _: [_HUMMUS])

    result = await tool.parse_order(
        ParseOrderIn(text="hummus, serve it with extra love", language=Language.EN),
        llm=llm,
    )

    assert len(result.items) == 1
    item = result.items[0]
    assert len(item.customizations) == 1, "Customization must NOT be silently dropped"
    assert item.customizations[0].kind == "other"
    assert item.customizations[0].text == "serve it with extra love"


@pytest.mark.asyncio
async def test_customization_missing_kind_falls_back_to_classifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the LLM omits kind, _classify_custom_kind provides a fallback."""
    from app.services.tools import parse_order as tool

    llm = _FakeMechanicalLLM(json.dumps({
        "items": [{
            "phrase": "hummus",
            "quantity": 1,
            "customizations": [{"text": "no onions please"}],
        }]
    }))
    monkeypatch.setattr("app.repositories.menu_repo.find_by_phrase", lambda _: [_HUMMUS])

    result = await tool.parse_order(
        ParseOrderIn(text="hummus no onions please", language=Language.EN),
        llm=llm,
    )

    assert len(result.items) == 1
    item = result.items[0]
    assert len(item.customizations) == 1, "Customization must NOT be dropped even without kind"
    # "no onions please" contains "no " so _classify_custom_kind → "remove"
    assert item.customizations[0].kind == "remove"
    assert item.customizations[0].text == "no onions please"


@pytest.mark.asyncio
async def test_unmappable_customization_added_to_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conversation service must NOT drop a kind='other' customization when adding to draft."""
    from app.services import conversation_service

    items_added: list[OrderItem] = []

    async def _fake_add_items(_self: Any, customer_id: Any, items: list[OrderItem]) -> None:
        items_added.extend(items)

    async def _fake_get_draft(_self: Any, customer_id: Any) -> None:
        return None

    async def _fake_update_last_seen(session: Any, customer_id: Any) -> None:
        pass

    weird_item = OrderItem(
        menu_item_id="cold_mezza_hummus",
        quantity=1,
        customizations=[Customization(kind="other", text="serve it in a clay pot")],
    )
    mock_parse = AsyncMock(
        return_value=ParseOrderOut(items=[weird_item], unresolved=[], confidence=0.9)
    )

    monkeypatch.setattr(
        "app.services.conversation_service.classify",
        lambda _text: (Intent.ORDER, 0.95),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.parse_order_tool",
        type("M", (), {"parse_order": mock_parse})(),
    )
    monkeypatch.setattr(
        "app.services.conversation_service.order_draft_service",
        type("M", (), {"add_items": _fake_add_items, "get_draft": _fake_get_draft})(),
    )
    monkeypatch.setattr(
        "app.repositories.transcript_repo.get_or_create_conversation",
        AsyncMock(return_value=Conversation(
            id=uuid4(),
            customer_id=_CUSTOMER_ID,
            started_at=datetime.now(tz=UTC),
            last_activity_at=datetime.now(tz=UTC),
        )),
    )
    monkeypatch.setattr("app.repositories.transcript_repo.append_turn", AsyncMock())
    monkeypatch.setattr("app.infra.draft_store.reset_failcount", AsyncMock())
    monkeypatch.setattr("app.infra.draft_store.incr_failcount", AsyncMock(return_value=0))
    monkeypatch.setattr("app.services.customer_service.update_last_seen", _fake_update_last_seen)

    class _FakeLLM:
        async def complete_mechanical(self, *, system: str, user: str, **kw: Any) -> str:
            return "{}"

        async def complete_synthesis(self, *, system: str, user: str, **kw: Any) -> str:
            return "OK"

    customer = Customer(id=_CUSTOMER_ID, telegram_user_id=1)
    await conversation_service.handle_text(
        session=AsyncMock(),
        customer=customer,
        telegram_chat_id=42,
        text="hummus please serve it in a clay pot",
        messenger=_FakeMessenger(),
        llm=_FakeLLM(),
    )

    assert len(items_added) == 1, "One item must have been added to the draft"
    added = items_added[0]
    assert added.menu_item_id == "cold_mezza_hummus"
    assert len(added.customizations) == 1, "kind='other' customization must NOT be dropped"
    assert added.customizations[0].kind == "other"
    assert added.customizations[0].text == "serve it in a clay pot"
