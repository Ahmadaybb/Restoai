from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Required — app refuses to boot when any of these are missing ──────────
    TELEGRAM_BOT_TOKEN: str
    GROQ_API_KEY: str
    VOYAGE_API_KEY: str
    DATABASE_URL: str
    REDIS_URL: str
    DISPATCHER_API_TOKEN: str

    # ── Optional webhook config (blank = long-polling in dev) ────────────────
    TELEGRAM_WEBHOOK_URL: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    TELEGRAM_WEBHOOK_SECRET_PATH: str = ""

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
