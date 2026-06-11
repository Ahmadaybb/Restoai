"""Readiness helpers — used by /readyz to check infrastructure dependencies."""
import logging

logger = logging.getLogger(__name__)


async def check_db() -> bool:
    try:
        from sqlalchemy import text

        from app.db.engine import get_engine

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning("readiness_db_failed", exc_info=True)
        return False


async def check_redis() -> bool:
    try:
        from app.infra.redis_client import get_redis

        await get_redis().ping()
        return True
    except Exception:
        logger.warning("readiness_redis_failed", exc_info=True)
        return False
