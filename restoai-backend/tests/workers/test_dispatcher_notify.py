"""Tests for Bug Fix 2 — dispatcher_notify sends a real Telegram alert.

Covers:
  1. _async_notify skips silently when DISPATCHER_TELEGRAM_CHAT_ID is not set.
  2. _async_notify sends an HTML alert containing the customer name and phone.
  3. _try_enqueue_notify enqueues the job via a sync Redis connection (not aioredis).
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ── _async_notify: skip when no chat_id ──────────────────────────────────────


@pytest.mark.asyncio
async def test_async_notify_skips_when_no_chat_id() -> None:
    """When DISPATCHER_TELEGRAM_CHAT_ID is empty, no DB access and no Telegram call."""
    from app.workers.jobs import _async_notify

    fake_settings = MagicMock()
    fake_settings.DISPATCHER_TELEGRAM_CHAT_ID = ""
    fake_settings.LOG_LEVEL = "INFO"

    engine_calls: list[str] = []
    bot_calls: list[dict] = []

    with (
        patch("app.infra.settings.get_settings", return_value=fake_settings),
        patch("app.infra.logging.configure_logging"),
        patch("sqlalchemy.ext.asyncio.create_async_engine", side_effect=lambda url: engine_calls.append(url)),
        patch("telegram.Bot", side_effect=lambda token: bot_calls.append(token)),
    ):
        await _async_notify(str(uuid4()))

    assert engine_calls == [], "No DB engine should be created when chat_id is unset"
    assert bot_calls == [], "No Bot should be instantiated when chat_id is unset"


# ── _async_notify: sends alert with customer info ─────────────────────────────


@pytest.mark.asyncio
async def test_async_notify_sends_alert_with_customer_info() -> None:
    """When chat_id is set, _async_notify sends an HTML message with name and phone."""
    from app.workers.jobs import _async_notify

    conv_id = str(uuid4())

    fake_settings = MagicMock()
    fake_settings.DISPATCHER_TELEGRAM_CHAT_ID = "987654321"
    fake_settings.TELEGRAM_BOT_TOKEN = "fake:token"
    fake_settings.DATABASE_URL = "postgresql+asyncpg://fake/db"
    fake_settings.LOG_LEVEL = "INFO"

    # Build fake DB row: (ConvORM, CustomerORM)
    fake_conv = MagicMock()
    fake_customer = MagicMock()
    fake_customer.display_name = "Lara Khalil"
    fake_customer.phone_e164 = "+96170999888"

    fake_result = MagicMock()
    fake_result.one_or_none.return_value = (fake_conv, fake_customer)

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=fake_result)

    @asynccontextmanager
    async def _fake_session_ctx():
        yield fake_session

    fake_factory = MagicMock(return_value=_fake_session_ctx())
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()

    sent: list[dict] = []

    fake_bot = AsyncMock()
    fake_bot.send_message = AsyncMock(side_effect=lambda **kw: sent.append(kw))

    with (
        patch("app.infra.settings.get_settings", return_value=fake_settings),
        patch("app.infra.logging.configure_logging"),
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=fake_engine),
        patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=fake_factory),
        patch("telegram.Bot", return_value=fake_bot),
    ):
        await _async_notify(conv_id)

    assert len(sent) == 1, "Expected exactly one Telegram message to be sent"
    msg = sent[0]
    assert msg["chat_id"] == 987654321
    assert "Lara Khalil" in msg["text"]
    assert "+96170999888" in msg["text"]
    assert msg.get("parse_mode") == "HTML"


# ── _try_enqueue_notify: uses sync Redis ─────────────────────────────────────


def test_try_enqueue_notify_enqueues_with_sync_redis() -> None:
    """_try_enqueue_notify must use sync redis.from_url (not aioredis) for the RQ connection."""
    from uuid import uuid4 as _uuid4

    conv_id = _uuid4()
    enqueued: list[tuple] = []

    fake_conn = MagicMock()
    fake_settings = MagicMock()
    fake_settings.REDIS_URL = "redis://localhost:6379/0"

    class _FakeQueue:
        def __init__(self, connection=None):
            self._conn = connection

        def enqueue(self, func, *args, **kwargs):
            enqueued.append((func, args, self._conn))

    with (
        patch("redis.from_url", return_value=fake_conn) as mock_from_url,
        patch("rq.Queue", _FakeQueue),
        patch("app.infra.settings.get_settings", return_value=fake_settings),
    ):
        from app.services.escalation_service import _try_enqueue_notify
        _try_enqueue_notify(conv_id)

    assert enqueued, "dispatcher_notify job was not enqueued"
    func_name, args, conn = enqueued[0]
    assert func_name == "app.workers.jobs.dispatcher_notify"
    assert args[0] == str(conv_id)
    # Verify sync redis.from_url was used (not aioredis)
    mock_from_url.assert_called_once_with("redis://localhost:6379/0")
    assert conn is fake_conn, "RQ Queue must receive the sync Redis connection"
