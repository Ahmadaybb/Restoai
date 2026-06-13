"""summarize_for_dispatcher tool — FR-025.

Synthesis-tier LLM call that produces a one-line summary of an escalated
conversation for the dispatcher escalation queue view.

Input:  SummarizeForDispatcherIn (transcript: list[Turn], draft: OrderDraft | None)
Output: SummarizeForDispatcherOut (summary: str)

contracts/internal_tools.md §summarize_for_dispatcher.
"""
import logging
from decimal import Decimal

from app.domain.clients import LLMClient
from app.domain.tools import SummarizeForDispatcherIn, SummarizeForDispatcherOut
from app.repositories import menu_repo

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are writing a one-line summary (≤120 chars) of an escalated restaurant
chat for a human dispatcher. Capture: what the customer tried to do, what
went wrong, and the current cart state. Be factual and terse.

Examples:
- "Customer struggled to describe delivery address; 2 hummus + 1 fattoush in cart,
  delivery pending."
- "Repeated dish not found; cart empty; no fulfillment set."
"""


def _draft_summary(inp: SummarizeForDispatcherIn) -> str:
    if inp.draft is None:
        return "no active cart"
    def _item_name(item_id: str) -> str:
        m = menu_repo.get_item(item_id)
        return m.name_en if m else item_id

    items_text = ", ".join(
        f"{it.quantity}x {_item_name(it.menu_item_id)}" for it in inp.draft.items
    )
    total = Decimal("0")
    for it in inp.draft.items:
        m = menu_repo.get_item(it.menu_item_id)
        if m:
            total += m.price_usd * it.quantity
    fulfillment = inp.draft.fulfillment or "fulfillment not set"
    return f"{items_text or 'no items'}, {fulfillment}, est. ${total:.2f}"


def _transcript_excerpt(inp: SummarizeForDispatcherIn) -> str:
    turns = list(inp.transcript)[-6:]
    lines = [f"[{t.sender}] {t.text[:120]}" for t in turns]
    return "\n".join(lines) if lines else "(no turns)"


async def summarize_for_dispatcher(
    inp: SummarizeForDispatcherIn,
    llm: LLMClient,
) -> SummarizeForDispatcherOut:
    draft_line = _draft_summary(inp)
    excerpt = _transcript_excerpt(inp)
    user_prompt = f"Cart: {draft_line}\n\nLast turns:\n{excerpt}"

    try:
        summary = await llm.complete_synthesis(
            system=_SYSTEM,
            user=user_prompt,
        )
        summary = summary.strip()[:200]
    except Exception:
        logger.warning("summarize_for_dispatcher_llm_failed")
        summary = draft_line

    return SummarizeForDispatcherOut(summary=summary)
