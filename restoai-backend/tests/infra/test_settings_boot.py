"""T019 — Settings must raise ValidationError when any required key is missing.

Constitution Principle V; research.md R12.
"""
import pytest
from pydantic import ValidationError

_BASE_ENV = {
    "TELEGRAM_BOT_TOKEN": "test-tok",
    "GROQ_API_KEY": "test-key",
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
    "REDIS_URL": "redis://localhost:6379/0",
    "DISPATCHER_API_TOKEN": "test-dispatch",
}


@pytest.mark.parametrize("missing_key", list(_BASE_ENV.keys()))
def test_missing_required_key_raises(monkeypatch: pytest.MonkeyPatch, missing_key: str) -> None:
    for k, v in _BASE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv(missing_key, raising=False)

    # Import fresh each time — avoid get_settings() lru_cache
    from app.infra import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    with pytest.raises(ValidationError):
        settings_mod.Settings()
    settings_mod.get_settings.cache_clear()
