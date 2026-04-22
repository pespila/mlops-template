from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from aipacken.config import get_settings
from aipacken.jobs.queues import FAST_QUEUE, QUEUE_FOR_FUNCTION

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
    """Route to the fast or slow queue based on the registered mapping.

    Unknown function names land on the fast queue — that's the safer
    default (fast queue has higher concurrency and shorter per-job
    timeouts so a misrouted long-running job will surface as a timeout
    instead of blocking every housekeeping job).
    """
    pool = await get_arq_pool()
    queue = QUEUE_FOR_FUNCTION.get(function, FAST_QUEUE)
    job = await pool.enqueue_job(function, *args, _queue_name=queue, **kwargs)
    return job.job_id if job else None
