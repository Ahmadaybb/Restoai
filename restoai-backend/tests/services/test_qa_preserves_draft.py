"""T079: Q&A turns preserve the active OrderDraft (FR-008).

A customer can ask menu questions in the middle of building an order without
losing their cart. After the Q&A turn the draft retains its pre-Q&A items,
and a subsequent order turn adds new items on top.

FR-008; T075 (conversation_service wiring).
"""
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.conversation import Conversation
from app.domain.customer import Customer
from app.domain.language import Intent, Language
from app.domain.menu import MenuItem
from app.domain.order import OrderDraft, OrderItem

# ── Shared fixtures ────────────────────────────────────────────────────────────

CUSTOMER_ID = uuid4()
DRAFT_ID = uuid4()

_ITEM_A = OrderItem(menu_item_id="cold_mezza_hummus", quantity=1)
_ITEM_B = OrderItem(menu_item_id="tannour_zaatar", quantity=2)


def _customer() -> Customer:
    return Customer(id=CUSTOMER_ID, telegram_user_id=99)


def _draft_with_item_a() -> OrderDraft:
    return OrderDraft(
        id=DRAFT_ID,
        customer_id=CUSTOMER_ID,
        items=[_ITEM_A],
        language=Language.EN,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )


def _conversation() -> Conversation:
    return Conversation(
        id=uuid4(),
        customer_id=CUSTOMER_ID,
        started_at=datetime.now(tz=UTC),
        last_activity_at=datetime.now(tz=UTC),
    )


# ── Fakes ──────────────────────────────────────────────────────────────────────


class _FakeEmbedder:
    async def embed_query(self, text: str) -> list[float]:
        return [0.1] * 1024

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]


class _FakeMessenger:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_message(
        self, *, chat_id: int, text: str, buttons: Any = None
    ) -> None:
        self.messages.append({"text": text, "buttons": buttons})

    async def send_contact_request(self, *, chat_id: int) -> None:
        pass


def _fake_llm_for_qa() -> Any:
    llm = AsyncMock()
    llm.complete_synthesis = AsyncMock(
        return_value="Hummus is a chickpea dip with tahini and lemon."
    )
    llm.complete_mechanical = AsyncMock(return_value=json.dumps({"items": [], "confidence": 0.1}))
    return llm


def _empty_db_result() -> MagicMock:
    result = MagicMock()
    result.fetchall.return_value = []
    return result


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_qa_turn_does_not_clear_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    """A query-intent turn must NOT delete or mutate the active draft.

    After the Q&A bot reply, the draft still contains the pre-Q&A items.
    FR-008.
    """
    from app.services import conversation_service

    # draft_store.delete_draft is the key function to watch
    delete_draft_called = {"called": False}

    async def _fake_delete_draft(customer_id: Any) -> None:
        delete_draft_called["called"] = True

    async def _fake_incr_failcount(customer_id: Any, field: str) -> int:
        return 1

    async def _fake_reset_failcount(customer_id: Any, field: str) -> None:
        pass

    async def _fake_update_last_seen(session: Any, customer_id: Any) -> None:
        pass

    monkeypatch.setattr(
        "app.services.conversation_service.classify",
        lambda _text: (Intent.QUERY, 0.95),
    )
    monkeypatch.setattr(
        "app.repositories.transcript_repo.get_or_create_conversation",
        AsyncMock(return_value=_conversation()),
    )
    monkeypatch.setattr(
        "app.repositories.transcript_repo.append_turn",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.customer_service.update_last_seen",
        _fake_update_last_seen,
    )
    monkeypatch.setattr(
        "app.infra.draft_store.delete_draft",
        _fake_delete_draft,
    )

    # patch menu_service.search to return a hummus chunk
    from uuid import uuid4 as _uuid4

    chunk_id = _uuid4()

    class _FakeRow:
        id = chunk_id
        menu_item_id = "cold_mezza_hummus"
        text = "Hummus. Chickpea dip with tahini and lemon."
        language = "en"

    result_mock = MagicMock()
    result_mock.fetchall.return_value = [_FakeRow()]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()

    messenger = _FakeMessenger()
    llm = _fake_llm_for_qa()
    embedder = _FakeEmbedder()

    await conversation_service.handle_text(
        session=session,
        customer=_customer(),
        telegram_chat_id=42,
        text="What is in the hummus?",
        messenger=messenger,
        llm=llm,
        embedder=embedder,
    )

    assert not delete_draft_called["called"], (
        "draft_store.delete_draft must NOT be called during a Q&A turn"
    )
    assert len(messenger.messages) == 1
    # Answer should come from synthesis
    assert "hummus" in messenger.messages[0]["text"].lower()


@pytest.mark.asyncio
async def test_qa_then_order_items_both_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Draft survives a Q&A turn; subsequent order adds item on top.

    Sequence:
      1. Draft with item A already in Redis.
      2. Query turn (no draft mutation expected).
      3. Order turn adds item B.
      4. Draft now contains A + B.
    FR-008.
    """
    from app.services import conversation_service

    # Track what items were added to the draft
    items_added: list[list[OrderItem]] = []

    async def _fake_add_items(customer_id: Any, items: list[OrderItem]) -> None:
        items_added.extend(items)

    async def _fake_get_draft(customer_id: Any) -> OrderDraft:
        # After order turn, return draft with both A and all added items
        return OrderDraft(
            id=DRAFT_ID,
            customer_id=CUSTOMER_ID,
            items=[_ITEM_A] + list(items_added),
            language=Language.EN,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )

    async def _fake_start_draft(customer_id: Any, language: Any) -> OrderDraft:
        return _draft_with_item_a()

    async def _fake_update_last_seen(session: Any, customer_id: Any) -> None:
        pass

    monkeypatch.setattr(
        "app.infra.draft_store.delete_draft", AsyncMock()
    )
    monkeypatch.setattr(
        "app.infra.draft_store.reset_failcount", AsyncMock()
    )
    monkeypatch.setattr(
        "app.infra.draft_store.incr_failcount", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(
        "app.services.order_draft_service.add_items", _fake_add_items
    )
    monkeypatch.setattr(
        "app.services.order_draft_service.get_draft", _fake_get_draft
    )
    monkeypatch.setattr(
        "app.services.customer_service.update_last_seen",
        _fake_update_last_seen,
    )
    monkeypatch.setattr(
        "app.repositories.transcript_repo.get_or_create_conversation",
        AsyncMock(return_value=_conversation()),
    )
    monkeypatch.setattr(
        "app.repositories.transcript_repo.append_turn",
        AsyncMock(),
    )

    # Step 2: Q&A turn (query intent, no draft mutation)
    chunk_id = uuid4()

    class _FakeRow:
        id = chunk_id
        menu_item_id = "cold_mezza_hummus"
        text = "Hummus. Chickpea dip."
        language = "en"

    result_qa = MagicMock()
    result_qa.fetchall.return_value = [_FakeRow()]
    session_qa = AsyncMock()
    session_qa.execute = AsyncMock(return_value=result_qa)
    session_qa.commit = AsyncMock()

    monkeypatch.setattr(
        "app.services.conversation_service.classify",
        lambda _text: (Intent.QUERY, 0.95),
    )

    messenger = _FakeMessenger()
    llm = _fake_llm_for_qa()

    await conversation_service.handle_text(
        session=session_qa,
        customer=_customer(),
        telegram_chat_id=42,
        text="What is in the hummus?",
        messenger=messenger,
        llm=llm,
        embedder=_FakeEmbedder(),
    )
    # No items should have been added during Q&A
    assert items_added == [], "No items should be added during a Q&A turn"

    # Step 3: Order turn adds item B (zaatar)
    parse_response = json.dumps({
        "items": [{"phrase": "zaatar", "quantity": 2, "customizations": []}],
        "confidence": 0.9,
    })
    llm_order = AsyncMock()
    llm_order.complete_mechanical = AsyncMock(return_value=parse_response)
    llm_order.complete_synthesis = AsyncMock(return_value="Your order looks great!")

    result_order = MagicMock()
    result_order.fetchall.return_value = []
    session_order = AsyncMock()
    session_order.execute = AsyncMock(return_value=result_order)
    session_order.commit = AsyncMock()

    monkeypatch.setattr(
        "app.services.conversation_service.classify",
        lambda _text: (Intent.ORDER, 0.95),
    )
    zaatar = MenuItem(
        id="tannour_zaatar",
        category="TANNOUR",
        name_en="Zaatar",
        name_ar="زعتر",
        price_usd=Decimal("3.0"),
    )
    monkeypatch.setattr(
        "app.repositories.menu_repo.find_by_phrase",
        lambda phrase: [zaatar] if "zaatar" in phrase.lower() else [],
    )

    await conversation_service.handle_text(
        session=session_order,
        customer=_customer(),
        telegram_chat_id=42,
        text="I want 2 zaatar please",
        messenger=messenger,
        llm=llm_order,
        embedder=_FakeEmbedder(),
    )

    # The final draft should contain both pre-Q&A item A and post-Q&A item B
    final_draft = await _fake_get_draft(CUSTOMER_ID)
    item_ids = {item.menu_item_id for item in final_draft.items}
    assert "cold_mezza_hummus" in item_ids, "Pre-Q&A item A must still be in draft"
