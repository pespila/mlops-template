"""Arq worker entrypoint.

Run with:
    arq aipacken.jobs.worker.WorkerSettings
"""

from arq.connections import RedisSettings

from aipacken.config import get_settings


async def ping(_ctx: dict) -> str:  # type: ignore[type-arg]
    return "pong"


class WorkerSettings:
    functions = [ping]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name = "platform:default"
    max_jobs = 10
