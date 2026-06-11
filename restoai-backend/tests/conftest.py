"""Shared pytest fixtures for the RestoAI test suite."""
import pytest


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Reset the lru_cache on get_settings() between tests."""
    from app.infra import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()
