"""Tests for classify_feedback sentiment classification tool."""
import pytest

from app.domain.feedback import Sentiment
from app.services.tools.classify_feedback import classify_feedback, _heuristic


# ── Heuristic (no LLM) ────────────────────────────────────────────────────────

def test_heuristic_5_star_is_good() -> None:
    assert _heuristic(5) == Sentiment.GOOD


def test_heuristic_4_star_is_good() -> None:
    assert _heuristic(4) == Sentiment.GOOD


def test_heuristic_3_star_is_neutral() -> None:
    assert _heuristic(3) == Sentiment.NEUTRAL


def test_heuristic_2_star_is_bad() -> None:
    assert _heuristic(2) == Sentiment.BAD


def test_heuristic_1_star_is_bad() -> None:
    assert _heuristic(1) == Sentiment.BAD


# ── classify_feedback: no comment (heuristic only) ───────────────────────────

@pytest.mark.asyncio
async def test_no_comment_star5_is_good() -> None:
    result = await classify_feedback(5, None, llm=None)  # type: ignore[arg-type]
    assert result == Sentiment.GOOD


@pytest.mark.asyncio
async def test_no_comment_star1_is_bad() -> None:
    result = await classify_feedback(1, None, llm=None)  # type: ignore[arg-type]
    assert result == Sentiment.BAD


@pytest.mark.asyncio
async def test_no_comment_star3_is_neutral() -> None:
    result = await classify_feedback(3, None, llm=None)  # type: ignore[arg-type]
    assert result == Sentiment.NEUTRAL


# ── classify_feedback: with LLM ──────────────────────────────────────────────

class _MockLLM:
    def __init__(self, response: str) -> None:
        self._response = response

    async def complete_mechanical(self, *, system: str, user: str, **kwargs: object) -> str:
        return self._response


@pytest.mark.asyncio
async def test_llm_returns_good() -> None:
    llm = _MockLLM("good")
    result = await classify_feedback(5, "Amazing food!", llm=llm)  # type: ignore[arg-type]
    assert result == Sentiment.GOOD


@pytest.mark.asyncio
async def test_llm_returns_bad() -> None:
    llm = _MockLLM("bad")
    result = await classify_feedback(1, "Terrible experience.", llm=llm)  # type: ignore[arg-type]
    assert result == Sentiment.BAD


@pytest.mark.asyncio
async def test_llm_returns_neutral() -> None:
    llm = _MockLLM("neutral")
    result = await classify_feedback(3, "It was okay.", llm=llm)  # type: ignore[arg-type]
    assert result == Sentiment.NEUTRAL


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_heuristic_good() -> None:
    class _FailingLLM:
        async def complete_mechanical(self, **kwargs: object) -> str:
            raise RuntimeError("LLM unavailable")

    result = await classify_feedback(5, "Great!", llm=_FailingLLM())  # type: ignore[arg-type]
    assert result == Sentiment.GOOD


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_heuristic_bad() -> None:
    class _FailingLLM:
        async def complete_mechanical(self, **kwargs: object) -> str:
            raise RuntimeError("LLM unavailable")

    result = await classify_feedback(1, "Awful.", llm=_FailingLLM())  # type: ignore[arg-type]
    assert result == Sentiment.BAD


@pytest.mark.asyncio
async def test_llm_returns_unexpected_value_falls_back() -> None:
    llm = _MockLLM("VERY_GOOD")  # unexpected value
    result = await classify_feedback(5, "Excellent!", llm=llm)  # type: ignore[arg-type]
    assert result == Sentiment.GOOD  # fallback heuristic for 5 stars
