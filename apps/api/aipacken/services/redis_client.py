from __future__ import annotations

from typing import Any

import redis.asyncio as redis_async

from aipacken.config import get_settings

_pool: redis_async.ConnectionPool | None = None


def get_pool() -> redis_async.ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = redis_async.ConnectionPool.from_url(
            settings.redis_url, decode_responses=True, max_connections=32
        )
    return _pool


def get_redis() -> redis_async.Redis:
    return redis_async.Redis(connection_pool=get_pool())


async def publish(channel: str, message: str | bytes | dict[str, Any]) -> int:
    import json as _json

    payload = message if isinstance(message, (str, bytes)) else _json.dumps(message)
    r = get_redis()
    return await r.publish(channel, payload)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.disconnect()
        _pool = None
