"""FastAPI application entry point.

Lifespan order:
  1. Validate Settings (hard boot failure on missing secrets).
  2. Configure structured JSON logging.
  3. Open async DB pool (asyncpg via SQLAlchemy).
  4. Open async Redis pool.
  5. Load IntentClassifier from joblib.
  6. Load EmbedderClient (sentence-transformers, CPU).
  7. Start TelegramClient in polling or webhook mode.

Constitution Principle V: if Settings() raises, the process exits before
serving any requests.
"""
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.middleware import RequestIdMiddleware
from app.db.engine import close_engine, init_engine
from app.infra.embed_client import EmbedderClient, load_embedder
from app.infra.intent_classifier import load_classifier
from app.infra.logging import configure_logging
from app.infra.redis_client import close_redis, init_redis
from app.infra.settings import get_settings

logger = logging.getLogger(__name__)

_telegram_client = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _telegram_client

    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    logger.info("restoai_starting")

    init_engine(settings.DATABASE_URL)
    init_redis(settings.REDIS_URL)

    load_classifier()

    load_embedder()
    app.state.embedder = EmbedderClient()

    from app.infra.telegram_client import TelegramClient

    _telegram_client = TelegramClient(
        bot_token=settings.TELEGRAM_BOT_TOKEN,
        webhook_url=settings.TELEGRAM_WEBHOOK_URL,
        webhook_secret=settings.TELEGRAM_WEBHOOK_SECRET,
        webhook_secret_path=settings.TELEGRAM_WEBHOOK_SECRET_PATH,
    )
    app.state.telegram = _telegram_client

    if _telegram_client.is_webhook_mode:
        await _telegram_client.set_webhook()
    else:
        logger.info("telegram_polling_mode")
        # Polling started externally via the telegram_router background task.

    logger.info("restoai_ready")

    yield

    # ── shutdown ──────────────────────────────────────────────────────────
    logger.info("restoai_shutting_down")
    if _telegram_client.is_webhook_mode:
        await _telegram_client.delete_webhook()
    else:
        await _telegram_client.stop()

    await close_engine()
    await close_redis()
    logger.info("restoai_stopped")


app = FastAPI(title="RestoAI Backend", lifespan=lifespan)
app.add_middleware(RequestIdMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
from app.api.dispatcher.escalations import router as dispatcher_escalations_router  # noqa: E402
from app.api.dispatcher.orders import router as dispatcher_orders_router  # noqa: E402
from app.api.health import router as health_router  # noqa: E402
from app.api.telegram_router import router as telegram_router  # noqa: E402

app.include_router(health_router)
app.include_router(dispatcher_orders_router)
app.include_router(dispatcher_escalations_router)
app.include_router(telegram_router)
