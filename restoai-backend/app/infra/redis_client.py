"""Async Redis client — thin wrapper around redis.asyncio.

Call init_redis(redis_url) once during app lifespan startup.
Use get_redis() everywhere else.
"""
import redis.asyncio as aioredis

# 2-hour TTL for all draft and failure-counter keys (research.md R6)
DRAFT_TTL = 7200

_pool: aioredis.Redis | None = None  # type: ignore[type-arg]


def init_redis(redis_url: str) -> "aioredis.Redis[str]":
    global _pool
    _pool = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    return _pool


def get_redis() -> "aioredis.Redis[str]":
    if _pool is None:
        raise RuntimeError("Redis not initialised; call init_redis() first.")
    return _pool


async def close_redis() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()  # type: ignore[attr-defined]
        _pool = None
