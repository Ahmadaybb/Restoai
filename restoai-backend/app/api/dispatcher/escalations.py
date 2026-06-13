"""Dispatcher escalation endpoints.

GET  /api/dispatcher/escalations          — list awaiting-human conversations
GET  /api/dispatcher/escalations/{id}     — full detail + DraftSummary + LLM summary
POST /api/dispatcher/escalations/{id}/take-over       — claim a conversation
POST /api/dispatcher/escalations/{id}/messages        — relay message to customer
POST /api/dispatcher/escalations/{id}/close-handoff   — return to bot

FR-024, FR-025, FR-026.
"""
import hashlib
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.dispatcher.auth import require_auth, validate_dispatcher_name
from app.services import dispatcher_service, escalation_service
from app.services.tools.summarize_for_dispatcher import summarize_for_dispatcher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dispatcher", tags=["dispatcher-escalations"])


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


_NOT_FOUND = HTTPException(
    status_code=404,
    detail={"code": "NOT_FOUND", "message": "Escalation not found"},
)

# ── Response schemas ──────────────────────────────────────────────────────────


class EscalationSummaryOut(BaseModel):
    conversation_id: UUID
    customer_name: str
    customer_phone: str
    started_at: datetime
    last_activity_at: datetime
    assigned_dispatcher_id: str | None = None


class TurnOut(BaseModel):
    id: UUID
    sender: str
    text: str
    language: str
    intent: str | None = None
    created_at: datetime


class DraftItemOut(BaseModel):
    menu_item_id: str
    quantity: int


class DraftSummaryOut(BaseModel):
    """T097 — lightweight Redis-draft snapshot surfaced in EscalationDetail."""
    fulfillment: str | None = None
    item_count: int
    items: list[DraftItemOut]
    address_text: str | None = None


class EscalationDetailOut(EscalationSummaryOut):
    awaiting_human: bool
    transcript: list[TurnOut]
    active_draft: DraftSummaryOut | None = None
    llm_summary: str | None = None


# ── Request schemas ───────────────────────────────────────────────────────────


class TakeOverRequest(BaseModel):
    dispatcher_name: str


class SendMessageRequest(BaseModel):
    dispatcher_name: str
    text: str


class CloseHandoffRequest(BaseModel):
    dispatcher_name: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _draft_summary_out(draft: Any) -> DraftSummaryOut | None:
    if draft is None:
        return None
    items = [DraftItemOut(menu_item_id=it.menu_item_id, quantity=it.quantity) for it in draft.items]
    addr_text: str | None = None
    if draft.address is not None:
        addr_text = draft.address.text_value or draft.address.area_label
    return DraftSummaryOut(
        fulfillment=draft.fulfillment,
        item_count=len(items),
        items=items,
        address_text=addr_text,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/escalations", response_model=dict)
async def list_escalations(
    token: str = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    pairs = await dispatcher_service.list_escalated(session)
    result = [
        EscalationSummaryOut(
            conversation_id=conv.id,
            customer_name=cust.display_name or "Unknown",
            customer_phone=cust.phone_e164 or "",
            started_at=conv.started_at,
            last_activity_at=conv.last_activity_at,
            assigned_dispatcher_id=conv.assigned_dispatcher_id,
        ).model_dump()
        for conv, cust in pairs
    ]
    return {"escalations": result}


@router.get("/escalations/{conversation_id}", response_model=EscalationDetailOut)
async def get_escalation(
    conversation_id: UUID,
    request: Request,
    token: str = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> EscalationDetailOut:
    detail = await dispatcher_service.get_escalation_detail(session, conversation_id)
    if detail is None:
        raise _NOT_FOUND
    conv, cust, turns, draft = detail

    transcript = [
        TurnOut(
            id=t.id,
            sender=t.sender,
            text=t.text,
            language=t.language.value if hasattr(t.language, "value") else str(t.language),
            intent=t.intent.value if t.intent else None,
            created_at=t.created_at,
        )
        for t in turns
    ]

    llm_summary: str | None = None
    state = getattr(request, "app", None)
    llm = getattr(getattr(state, "state", None), "llm", None)
    if llm is not None:
        try:
            from app.domain.tools import SummarizeForDispatcherIn
            result = await summarize_for_dispatcher(
                SummarizeForDispatcherIn(transcript=turns, draft=draft),
                llm=llm,
            )
            llm_summary = result.summary
        except Exception:
            logger.warning("summarize_for_dispatcher_failed")

    return EscalationDetailOut(
        conversation_id=conv.id,
        customer_name=cust.display_name or "Unknown",
        customer_phone=cust.phone_e164 or "",
        started_at=conv.started_at,
        last_activity_at=conv.last_activity_at,
        assigned_dispatcher_id=conv.assigned_dispatcher_id,
        awaiting_human=conv.awaiting_human,
        transcript=transcript,
        active_draft=_draft_summary_out(draft),
        llm_summary=llm_summary,
    )


@router.post("/escalations/{conversation_id}/take-over", status_code=200)
async def take_over(
    conversation_id: UUID,
    body: TakeOverRequest,
    token: str = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    dispatcher_name = validate_dispatcher_name(body.dispatcher_name)
    dispatcher_id = _hash_token(token)
    detail = await dispatcher_service.get_escalation_detail(session, conversation_id)
    if detail is None:
        raise _NOT_FOUND
    await escalation_service.take_over(
        session, conversation_id, dispatcher_id, dispatcher_name
    )
    return {"status": "ok"}


@router.post("/escalations/{conversation_id}/messages", status_code=200)
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    request: Request,
    token: str = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    dispatcher_name = validate_dispatcher_name(body.dispatcher_name)
    if not body.text or not body.text.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "TEXT_REQUIRED", "message": "text must not be blank"},
        )
    state = getattr(request, "app", None)
    telegram = getattr(getattr(state, "state", None), "telegram", None)
    if telegram is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "MESSENGER_UNAVAILABLE", "message": "Telegram client not initialised"},
        )
    await dispatcher_service.send_message(
        session,
        conversation_id=conversation_id,
        text=body.text.strip(),
        dispatcher_token=token,
        dispatcher_name=dispatcher_name,
        messenger=telegram,
    )
    return {"status": "ok"}


@router.post("/escalations/{conversation_id}/close-handoff", status_code=200)
async def close_handoff(
    conversation_id: UUID,
    body: CloseHandoffRequest,
    token: str = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    dispatcher_name = validate_dispatcher_name(body.dispatcher_name)
    dispatcher_id = _hash_token(token)
    detail = await dispatcher_service.get_escalation_detail(session, conversation_id)
    if detail is None:
        raise _NOT_FOUND
    conv, cust, _turns, _draft = detail
    await escalation_service.close_handoff(
        session,
        conversation_id=conversation_id,
        customer_id=conv.customer_id,
        dispatcher_id=dispatcher_id,
        dispatcher_name=dispatcher_name,
    )
    return {"status": "ok"}
