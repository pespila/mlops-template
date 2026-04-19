from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from aipacken.config import get_settings

_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def close_arq_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def enqueue(function: str, *args: Any, **kwargs: Any) -> str | None:
    pool = await get_arq_pool()
    job = await pool.enqueue_job(function, *args, _queue_name="platform:default", **kwargs)
    return job.job_id if job else None
