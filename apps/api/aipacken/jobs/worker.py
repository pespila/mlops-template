"""Arq worker entrypoint.

Run with:
    arq aipacken.jobs.worker.WorkerSettings
"""

from __future__ import annotations

from typing import Any

import structlog
from arq.connections import RedisSettings
from arq.worker import func

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


# Per-function timeouts + retry budgets. Previously everything shared a single
# 3-hour timeout + no retry ceiling (perf.md P0: 'Arq worker is a ticking
# bomb'). Each category now has a cap that matches its real work:
#   * fast housekeeping: seconds-scale, retry on flake
#   * long training: matches settings.training_job_timeout_seconds
#   * deploy / packaging: minutes-scale, a single retry covers transient
#     Docker / builder hiccups
#
# max_tries=1 for cleanup/teardown so a failed delete does not thrash.

_settings = get_settings()
_TRAIN_TIMEOUT = _settings.training_job_timeout_seconds  # 7200 by default

_FUNCTIONS = [
    ping,
    func(profile_dataset.profile_dataset, timeout=600, max_tries=3),
    func(train_run.train_run, timeout=_TRAIN_TIMEOUT, max_tries=2),
    func(analyze_run.analyze_run, timeout=1800, max_tries=2),
    func(deploy_model.deploy_model, timeout=600, max_tries=3),
    func(teardown_deployment.teardown_deployment, timeout=120, max_tries=1),
    func(cleanup.cleanup, timeout=300, max_tries=1),
    func(build_package.build_package, timeout=1800, max_tries=2),
]


class WorkerSettings:
    functions = _FUNCTIONS
    cron_jobs: list[Any] = []
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name = "platform:default"
    # 4 concurrent trainers is a more honest ceiling than 10 — each trainer
    # can eat a whole CPU core + several GB of RAM, so 10 in flight on a
    # single-node box will OOM the host before the queue drains.
    max_jobs = 4
    # Retry delay floor for the whole worker. Per-function max_tries override
    # the try count; this controls how long arq waits between attempts.
    retry_jobs = True
    # Global upper bound — any single function's `timeout` still wins; this
    # is the failsafe so a function without an explicit timeout cannot pin
    # a slot for longer than the slowest real task.
    job_timeout = _TRAIN_TIMEOUT
