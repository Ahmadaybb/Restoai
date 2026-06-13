"""T067: Dispatcher API schema validation tests.

Covers:
- dispatcher_name missing → 400 DISPATCHER_NAME_REQUIRED
- dispatcher_name empty / whitespace-only → 400
- dispatcher_name > 80 chars → 400
- valid dispatcher_name passes
"""
import pytest
from fastapi import HTTPException

from app.api.dispatcher.auth import validate_dispatcher_name

# ─── validate_dispatcher_name unit tests ──────────────────────────────────────


def test_valid_dispatcher_name() -> None:
    assert validate_dispatcher_name("Alice") == "Alice"


def test_dispatcher_name_trimmed() -> None:
    assert validate_dispatcher_name("  Bob  ") == "Bob"


def test_dispatcher_name_none_raises_400() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_dispatcher_name(None)
    assert exc_info.value.status_code == 400
    assert "DISPATCHER_NAME_REQUIRED" in str(exc_info.value.detail)


def test_dispatcher_name_empty_raises_400() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_dispatcher_name("")
    assert exc_info.value.status_code == 400


def test_dispatcher_name_whitespace_only_raises_400() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_dispatcher_name("   ")
    assert exc_info.value.status_code == 400


def test_dispatcher_name_too_long_raises_400() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_dispatcher_name("X" * 81)
    assert exc_info.value.status_code == 400
    assert "DISPATCHER_NAME_REQUIRED" in str(exc_info.value.detail)


def test_dispatcher_name_exactly_80_chars_allowed() -> None:
    name = "A" * 80
    assert validate_dispatcher_name(name) == name


def test_dispatcher_name_81_chars_rejected() -> None:
    with pytest.raises(HTTPException):
        validate_dispatcher_name("A" * 81)


# ─── Auth bearer token tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_require_auth_wrong_token_raises_401(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.security import HTTPAuthorizationCredentials

    from app.api.dispatcher.auth import require_auth
    from app.infra import settings as settings_mod

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("GROQ_API_KEY", "key")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost")
    monkeypatch.setenv("DISPATCHER_API_TOKEN", "correct-token")
    settings_mod.get_settings.cache_clear()

    bad_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong-token")
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(bad_creds)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_auth_correct_token_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.security import HTTPAuthorizationCredentials

    from app.api.dispatcher.auth import require_auth
    from app.infra import settings as settings_mod

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("GROQ_API_KEY", "key")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost")
    monkeypatch.setenv("DISPATCHER_API_TOKEN", "correct-token")
    settings_mod.get_settings.cache_clear()

    good_creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="correct-token")
    result = await require_auth(good_creds)
    assert result == "correct-token"
