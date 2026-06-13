"""RQ background jobs.

dispatcher_notify: fired by escalation_service when awaiting_human is set;
  logs the escalation event so the dispatcher dashboard can poll or receive
  a push notification via an external webhook (FR-024, FR-025).
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


def dispatcher_notify(conversation_id: str) -> None:
    """Best-effort notification job — runs in the RQ worker process."""
    asyncio.run(_async_notify(conversation_id))


async def _async_notify(conversation_id: str) -> None:
    try:
        from app.infra.logging import configure_logging
        from app.infra.settings import get_settings

        settings = get_settings()
        configure_logging(settings.LOG_LEVEL)
        logger.info(
            "dispatcher_notify",
            extra={"conversation_id": conversation_id},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "dispatcher_notify_failed",
            extra={"conversation_id": conversation_id, "error": str(exc)},
        )
