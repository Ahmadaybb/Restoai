"""extract_address tool — FR-010, FR-035.

Mechanical-tier LLM extracts a structured address from a customer message.
area_confidence < 0.7 → area_label set to null (don't warn per R8).
"""
import json
import logging

from app.domain.clients import LLMClient
from app.domain.tools import ExtractAddressIn, ExtractAddressOut

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are an address extraction assistant for a Lebanese restaurant chatbot.
Extract delivery address information from the customer's message.

Respond with ONLY valid JSON matching this schema:
{
  "kind": "text" | "location",
  "text_value": string or null,
  "area_label": string or null,
  "area_confidence": float 0.0-1.0
}

Rules:
- kind is always "text" unless the message contains GPS coordinates.
- text_value: the full address as given by the customer.
- area_label: the Beirut neighborhood/area name (e.g. "Hamra", "Achrafieh",
  "Verdun"). Extract only if clearly identifiable. Null if uncertain.
- area_confidence: your confidence that area_label is correct (0.7+ = confident).
  Set to 0.0 if area_label is null.
"""


async def extract_address(
    inp: ExtractAddressIn,
    llm: LLMClient,
) -> ExtractAddressOut:
    try:
        raw = await llm.complete_mechanical(
            system=_SYSTEM,
            user=inp.text[:1000],
            response_format=dict,
        )
        data = json.loads(raw)
        area_confidence = float(data.get("area_confidence", 0.0))
        area_label: str | None = data.get("area_label")
        if area_confidence < 0.7:
            area_label = None
            area_confidence = 0.0
        return ExtractAddressOut(
            kind=data.get("kind", "text"),
            text_value=data.get("text_value") or inp.text,
            area_label=area_label,
            area_confidence=area_confidence,
        )
    except Exception:
        logger.warning("extract_address_failed", extra={"text_len": len(inp.text)})
        return ExtractAddressOut(
            kind="text",
            text_value=inp.text,
            area_label=None,
            area_confidence=0.0,
        )
