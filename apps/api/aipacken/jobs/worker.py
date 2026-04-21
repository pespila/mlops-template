"""Arq worker entrypoint.

Run with:
    arq aipacken.jobs.worker.WorkerSettings
"""

from __future__ import annotations

from typing import Any

import structlog
from arq.connections import RedisSettings

from aipacken.config import get_settings
from aipacken.db import SessionLocal
from aipacken.jobs.tasks import (
    analyze_run,
    build_package,
    cleanup,
    deploy_model,
    profile_dataset,
    teardown_deployment,
    train_run,
)
from aipacken.services.redis_client import close_pool, get_redis

logger = structlog.get_logger(__name__)


async def ping(_ctx: dict[str, Any]) -> str:
    return "pong"


async def startup(ctx: dict[str, Any]) -> None:
    ctx["session_factory"] = SessionLocal
    ctx["redis"] = get_redis()
    logger.info("worker.startup")


async def shutdown(ctx: dict[str, Any]) -> None:
    await close_pool()
    logger.info("worker.shutdown")


class WorkerSettings:
    functions = [
        ping,
        profile_dataset.profile_dataset,
        train_run.train_run,
        analyze_run.analyze_run,
        deploy_model.deploy_model,
        teardown_deployment.teardown_deployment,
        cleanup.cleanup,
        build_package.build_package,
    ]
    cron_jobs: list[Any] = []
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name = "platform:default"
    max_jobs = 10
    job_timeout = 60 * 60 * 3
