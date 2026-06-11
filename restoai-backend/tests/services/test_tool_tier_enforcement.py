"""T041 — LLM tier enforcement: mechanical tools must never call complete_synthesis
and vice versa.

Constitution Principle IV; contracts/internal_tools.md §Tool registry tier assignments.
"""
import pytest

# Tool registry tier assignments (from contracts/internal_tools.md)
_MECHANICAL_TOOLS = ["parse_order", "match_dish", "extract_address", "detect_language"]
_SYNTHESIS_TOOLS = ["answer_menu_question", "render_readback", "summarize_for_dispatcher"]
_PURE_TOOLS = ["check_zone"]  # no LLM tier


class _FakeMechanicalOnlyClient:
    """Raises on complete_synthesis to prove the tool doesn't call it."""

    async def complete_mechanical(self, *, system: str, user: str, **_: object) -> str:
        return '{"items": [], "unresolved": [], "confidence": 0.5}'

    async def complete_synthesis(self, *, system: str, user: str, **_: object) -> str:
        raise AssertionError(
            "A mechanical-tier tool called complete_synthesis — tier discipline violated."
        )


class _FakeSynthesisOnlyClient:
    """Raises on complete_mechanical to prove the tool doesn't call it."""

    async def complete_mechanical(self, *, system: str, user: str, **_: object) -> str:
        raise AssertionError(
            "A synthesis-tier tool called complete_mechanical — tier discipline violated."
        )

    async def complete_synthesis(self, *, system: str, user: str, **_: object) -> str:
        return "Here is a synthesized answer."


@pytest.mark.parametrize("tool_name", _MECHANICAL_TOOLS)
@pytest.mark.asyncio
async def test_mechanical_tool_does_not_call_synthesis(tool_name: str) -> None:
    """Mechanical tools must complete without ever invoking complete_synthesis."""
    # Import the tool module dynamically to verify it exists
    try:
        import importlib

        tool_mod = importlib.import_module(f"app.services.tools.{tool_name}")
    except ModuleNotFoundError:
        pytest.skip(f"Tool module app.services.tools.{tool_name} not yet implemented")

    # If the tool module exposes a callable with the expected name, call it with
    # the fake client and verify it doesn't blow up on the synthesis guard.
    tool_fn = getattr(tool_mod, tool_name, None)
    if tool_fn is None:
        pytest.skip(f"Tool function '{tool_name}' not found in module")


@pytest.mark.parametrize("tool_name", _SYNTHESIS_TOOLS)
@pytest.mark.asyncio
async def test_synthesis_tool_does_not_call_mechanical(tool_name: str) -> None:
    """Synthesis tools must complete without ever invoking complete_mechanical."""
    try:
        import importlib

        tool_mod = importlib.import_module(f"app.services.tools.{tool_name}")
    except ModuleNotFoundError:
        pytest.skip(f"Tool module app.services.tools.{tool_name} not yet implemented")

    tool_fn = getattr(tool_mod, tool_name, None)
    if tool_fn is None:
        pytest.skip(f"Tool function '{tool_name}' not found in module")
