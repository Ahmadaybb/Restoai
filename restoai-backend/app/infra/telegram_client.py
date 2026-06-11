"""Telegram Bot client — python-telegram-bot v21+ wrapper.

Selects long-polling (dev) or webhook (prod) based on Settings.TELEGRAM_WEBHOOK_URL.
Implements app.domain.clients.MessengerClient protocol.

Security (contracts/telegram_webhook.md):
  - Webhook endpoint uses a secret path segment (TELEGRAM_WEBHOOK_SECRET_PATH).
  - X-Telegram-Bot-Api-Secret-Token header is compared constant-time.
"""
import hmac
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, ApplicationBuilder

logger = logging.getLogger(__name__)


class TelegramClient:
    """Async Telegram client — polling or webhook mode."""

    def __init__(
        self,
        bot_token: str,
        webhook_url: str = "",
        webhook_secret: str = "",
        webhook_secret_path: str = "",
    ) -> None:
        self._bot_token = bot_token
        self._webhook_url = webhook_url
        self._webhook_secret = webhook_secret
        self._webhook_secret_path = webhook_secret_path
        self._app: Application | None = None  # type: ignore[type-arg]

    @property
    def is_webhook_mode(self) -> bool:
        return bool(self._webhook_url)

    def verify_webhook_secret(self, token_header: str) -> bool:
        """Constant-time comparison of the X-Telegram-Bot-Api-Secret-Token header."""
        return hmac.compare_digest(
            token_header.encode(), self._webhook_secret.encode()
        )

    async def start_polling(
        self,
        update_handler: Callable[[Update, Any], Coroutine[Any, Any, None]],
    ) -> None:
        """Start long-polling loop in the background (dev mode)."""
        from telegram.ext import CallbackQueryHandler, MessageHandler, filters

        self._app = (
            ApplicationBuilder().token(self._bot_token).build()
        )
        self._app.add_handler(
            MessageHandler(filters.ALL, update_handler)
        )
        self._app.add_handler(
            CallbackQueryHandler(update_handler)
        )
        logger.info("telegram_polling_started")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()  # type: ignore[union-attr]

    async def set_webhook(self) -> None:
        """Register the webhook URL with Telegram (prod mode)."""
        bot = Bot(token=self._bot_token)
        webhook_url = (
            f"{self._webhook_url.rstrip('/')}"
            f"/telegram/webhook/{self._webhook_secret_path}"
        )
        await bot.set_webhook(
            url=webhook_url,
            secret_token=self._webhook_secret,
        )
        logger.info("telegram_webhook_set", extra={"url": webhook_url})

    async def delete_webhook(self) -> None:
        bot = Bot(token=self._bot_token)
        await bot.delete_webhook()
        logger.info("telegram_webhook_deleted")

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        buttons: list[dict[str, str]] | None = None,
    ) -> None:
        bot = Bot(token=self._bot_token)
        reply_markup = None
        if buttons:
            keyboard = [
                [InlineKeyboardButton(b["label"], callback_data=b["callback_data"])]
                for b in buttons
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

    async def send_contact_request(self, *, chat_id: int) -> None:
        from telegram import KeyboardButton, ReplyKeyboardMarkup

        bot = Bot(token=self._bot_token)
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Share my phone number", request_contact=True)]],
            one_time_keyboard=True,
            resize_keyboard=True,
        )
        await bot.send_message(
            chat_id=chat_id,
            text="Please share your phone number to continue.",
            reply_markup=keyboard,
        )

    async def stop(self) -> None:
        if self._app is not None:
            await self._app.updater.stop()  # type: ignore[union-attr]
            await self._app.stop()
            await self._app.shutdown()
