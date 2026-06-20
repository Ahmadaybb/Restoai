"""Dispatcher REST surface for feedback.

GET /api/dispatcher/feedback — paginated list with sentiment/status filters.
"""
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.dispatcher.auth import require_auth
from app.services import feedback_service, menu_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dispatcher", tags=["dispatcher"])


def _items_summary(items_snapshot: list[Any]) -> str:
    parts = []
    for item in items_snapshot:
        mi = menu_service.get_item(item.get("menu_item_id", ""))
        name = mi.name_en if mi else item.get("menu_item_id", "")
        parts.append(f"{item.get('quantity', 1)}× {name}")
    return ", ".join(parts) if parts else ""


@router.get("/feedback", response_model=dict)
async def list_feedback(
    sentiment: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    token: str = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    rows = await feedback_service.list_feedback(
        session,
        limit=limit,
        offset=offset,
        sentiment=sentiment,
        status=status,
    )
    total = await feedback_service.count_feedback(session, sentiment=sentiment, status=status)
    summary = await feedback_service.get_summary(session)

    return {
        "feedback": [
            {
                "id": str(row.feedback.id),
                "order_id": str(row.feedback.order_id),
                "order_short_id": str(row.feedback.order_id)[:8].upper(),
                "customer_name": row.customer_name or "Unknown",
                "customer_phone": row.customer_phone or "",
                "items_summary": _items_summary(row.items_snapshot),
                "star_rating": row.feedback.star_rating,
                "comment": row.feedback.comment,
                "sentiment": row.feedback.sentiment,
                "status": str(row.feedback.status),
                "feedback_requested_at": row.feedback.feedback_requested_at.isoformat(),
                "responded_at": (
                    row.feedback.responded_at.isoformat()
                    if row.feedback.responded_at
                    else None
                ),
            }
            for row in rows
        ],
        "total": total,
        "summary": summary,
    }
