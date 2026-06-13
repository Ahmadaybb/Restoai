"""render_readback tool — FR-016.

Synthesis-tier LLM renders a localized order read-back with line items,
customizations, fulfillment, address, and estimated total.
Includes the mandatory "final pricing is confirmed by the dispatcher" line.
"""
import logging
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from app.domain.clients import LLMClient
from app.domain.language import Language
from app.domain.tools import ReadbackButton, RenderReadbackIn, RenderReadbackOut
from app.repositories import menu_repo

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


@lru_cache(maxsize=8)
def _load_system_prompt(lang_dir: str) -> str:
    path = _PROMPTS_DIR / lang_dir / "render_readback.txt"
    return path.read_text(encoding="utf-8")


def _system_for(language: Language) -> str:
    lang_dir = "ar_lb" if language == Language.AR_LB else "en"
    return _load_system_prompt(lang_dir)


def _compute_total(inp: RenderReadbackIn) -> Decimal:
    total = Decimal("0")
    for item in inp.draft.items:
        menu_item = menu_repo.get_item(item.menu_item_id)
        if menu_item:
            total += menu_item.price_usd * item.quantity
    return total


def _build_summary(inp: RenderReadbackIn) -> str:
    lines = []
    for item in inp.draft.items:
        menu_item = menu_repo.get_item(item.menu_item_id)
        name = menu_item.name_en if menu_item else item.menu_item_id
        lines.append(f"- {item.quantity}x {name}")
        for c in item.customizations:
            lines.append(f"  • {c.text}")
    fulfillment_line = f"Fulfillment: {inp.draft.fulfillment}" if inp.draft.fulfillment else ""
    addr_line = ""
    if inp.draft.address:
        if inp.draft.address.text_value:
            addr_line = f"Address: {inp.draft.address.text_value}"
        elif inp.draft.address.lat:
            addr_line = f"Location: {inp.draft.address.lat}, {inp.draft.address.lon}"
    total = _compute_total(inp)
    summary_lines = lines + [fulfillment_line, addr_line, f"Estimated total: ${total:.2f}"]
    return "\n".join(filter(None, summary_lines))


async def render_readback(
    inp: RenderReadbackIn,
    llm: LLMClient,
) -> RenderReadbackOut:
    summary = _build_summary(inp)
    system = _system_for(inp.language)

    try:
        text = await llm.complete_synthesis(
            system=system,
            user=f"Order summary to render:\n{summary}",
        )
    except Exception:
        logger.warning("render_readback_llm_failed")
        text = f"{summary}\n\nNote: final pricing is confirmed by the dispatcher."

    draft_id = str(inp.draft.id)
    buttons = [
        ReadbackButton(label="✅ Confirm", callback_data=f"confirm:{draft_id}"),
        ReadbackButton(label="✏️ Edit", callback_data=f"edit:{draft_id}"),
    ]
    return RenderReadbackOut(text=text, buttons=buttons)
