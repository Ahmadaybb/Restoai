"""T078: No-fabrication guarantee for answer_menu_question.

When retrieval returns no chunks for a dish absent from the menu,
answer_menu_question MUST return the no-info fallback with empty citations
and MUST NOT call the synthesis LLM (so it can never invent content).

FR-007; contracts/internal_tools.md §answer_menu_question.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.language import Language
from app.domain.tools import AnswerMenuQuestionIn
from app.services.tools.answer_menu_question import (
    _NO_INFO_AR,
    _NO_INFO_EN,
    answer_menu_question,
)

# ── Fakes ──────────────────────────────────────────────────────────────────────


class _FakeEmbedder:
    """Returns a zero vector so search never actually embeds."""

    async def embed_query(self, text: str) -> list[float]:
        return [0.0] * 1024

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1024 for _ in texts]


class _FakeLLMShouldNotBeCalled:
    """Raises if called — verifies synthesis LLM is never invoked on no-hit path."""

    async def complete_mechanical(self, *, system: str, user: str, **kw: object) -> str:
        raise AssertionError("complete_mechanical must not be called on no-hit path")

    async def complete_synthesis(self, *, system: str, user: str, **kw: object) -> str:
        raise AssertionError("complete_synthesis must not be called on no-hit path")


def _make_empty_session() -> AsyncMock:
    """AsyncSession mock whose execute returns a result with no rows."""
    result = MagicMock()
    result.fetchall.return_value = []
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_absent_dish_returns_no_info_english() -> None:
    """Dish not in the menu → no-info English reply, empty citations, no LLM call."""
    session = _make_empty_session()
    inp = AnswerMenuQuestionIn(
        question="What is in the dragon roll sushi?",
        language=Language.EN,
    )
    result = await answer_menu_question(
        inp,
        session=session,
        embedder=_FakeEmbedder(),
        llm=_FakeLLMShouldNotBeCalled(),
    )

    assert result.citations == []
    assert "I don't have info" in result.answer
    assert result.answer == _NO_INFO_EN


@pytest.mark.asyncio
async def test_absent_dish_returns_no_info_arabic() -> None:
    """Same guarantee in Arabic."""
    session = _make_empty_session()
    inp = AnswerMenuQuestionIn(
        question="ما هو السوشي؟",
        language=Language.AR_LB,
    )
    result = await answer_menu_question(
        inp,
        session=session,
        embedder=_FakeEmbedder(),
        llm=_FakeLLMShouldNotBeCalled(),
    )

    assert result.citations == []
    assert result.answer == _NO_INFO_AR


@pytest.mark.asyncio
async def test_no_fabrication_llm_never_called_on_empty_retrieval() -> None:
    """Confirms the synthesis LLM is bypassed entirely when retrieval is empty."""
    llm_call_count = {"synthesis": 0, "mechanical": 0}

    class _TrackingLLM:
        async def complete_mechanical(self, *, system: str, user: str, **kw: object) -> str:
            llm_call_count["mechanical"] += 1
            return "unexpected"

        async def complete_synthesis(self, *, system: str, user: str, **kw: object) -> str:
            llm_call_count["synthesis"] += 1
            return "invented: dragon roll costs $5, has seaweed"

    session = _make_empty_session()
    inp = AnswerMenuQuestionIn(question="Tell me about the pizza", language=Language.EN)
    await answer_menu_question(
        inp,
        session=session,
        embedder=_FakeEmbedder(),
        llm=_TrackingLLM(),
    )

    assert llm_call_count["synthesis"] == 0, "LLM synthesis must not run when retrieval is empty"
    assert llm_call_count["mechanical"] == 0


@pytest.mark.asyncio
async def test_with_hits_calls_synthesis_and_returns_citations() -> None:
    """When chunks are found, synthesis is called and citations are populated."""
    from uuid import uuid4

    chunk_id = uuid4()

    class _FakeRow:
        def __init__(self) -> None:
            self.id = chunk_id
            self.menu_item_id = "cold_mezza_hummus"
            self.text = "Hummus. Chickpea dip with tahini and lemon. Category: COLD MEZZA. Price: $7.00"
            self.language = "en"

    result_mock = MagicMock()
    result_mock.fetchall.return_value = [_FakeRow()]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)

    synthesis_called = {"called": False}

    class _FakeLLMWithSynthesis:
        async def complete_mechanical(self, *, system: str, user: str, **kw: object) -> str:
            return "not needed"

        async def complete_synthesis(self, *, system: str, user: str, **kw: object) -> str:
            synthesis_called["called"] = True
            return "Hummus is a chickpea dip with tahini and lemon, priced at $7.00."

    inp = AnswerMenuQuestionIn(question="What is hummus?", language=Language.EN)
    result = await answer_menu_question(
        inp,
        session=session,
        embedder=_FakeEmbedder(),
        llm=_FakeLLMWithSynthesis(),
    )

    assert synthesis_called["called"]
    assert len(result.citations) == 1
    assert result.citations[0].menu_item_id == "cold_mezza_hummus"
    assert result.citations[0].chunk_id == chunk_id
    assert "hummus" in result.answer.lower()
