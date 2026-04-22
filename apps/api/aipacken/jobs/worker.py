"""Arq worker entrypoints — separate 'fast' and 'slow' queues.

One worker pool on a single queue used to back all seven jobs. A long
training run (hours) would starve the housekeeping queue, and a flaky
deploy would share retry budget with a cleanup. Split into two queues
so the two workloads contend for resources independently:

* FastWorkerSettings handles seconds-scale housekeeping:
  ping, profile_dataset, deploy_model, teardown_deployment, cleanup.
  Higher concurrency (4 simultaneous), lower per-job timeout, quicker
  retries.

* SlowWorkerSettings handles minutes-to-hours ML workloads:
  train_run, analyze_run, build_package.
  Lower concurrency (2) to respect per-job memory budgets, full
  training-job-timeout ceiling.

Both invoke the same startup/shutdown to wire ctx['session_factory'] +
ctx['redis']. The compose file runs two worker services
(worker-fast + worker-slow) so arq processes are isolated too — a
hung trainer can no longer pin a slot that a cleanup job needs.

Run with:
    arq aipacken.jobs.worker.FastWorkerSettings
    arq aipacken.jobs.worker.SlowWorkerSettings

Legacy `WorkerSettings` is kept for dev / single-worker compose overlays
and registers every function — falls back to the old one-queue behaviour
if ``make dev`` only spawns one worker.
"""

from __future__ import annotations

from typing import Any

import structlog
from arq.connections import RedisSettings
from arq.worker import func

from aipacken.config import get_settings
from aipacken.db import SessionLocal
from aipacken.jobs.queues import FAST_QUEUE, QUEUE_FOR_FUNCTION, SLOW_QUEUE
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

# Re-export for callers that imported from worker.py historically.
__all__ = [
    "FAST_QUEUE",
    "QUEUE_FOR_FUNCTION",
    "SLOW_QUEUE",
    "FastWorkerSettings",
    "SlowWorkerSettings",
    "WorkerSettings",
    "ping",
    "shutdown",
    "startup",
]


async def ping(_ctx: dict[str, Any]) -> str:
    return "pong"


async def startup(ctx: dict[str, Any]) -> None:
    ctx["session_factory"] = SessionLocal
    ctx["redis"] = get_redis()
    # Same auto-instrumentation as the api. httpx / redis / sqlalchemy
    # spans cover the real per-job work; train_run.py's docker calls go
    # through httpx → builder → docker so they show up end-to-end.
    try:
        from aipacken.observability import init_tracing

        init_tracing(service_name="aipacken-worker")
    except Exception as exc:
        logger.warning("worker.otel.init_failed", error=str(exc))
    logger.info("worker.startup", queue=ctx.get("queue_name"))


async def shutdown(ctx: dict[str, Any]) -> None:
    await close_pool()
    logger.info("worker.shutdown")


_settings = get_settings()
_TRAIN_TIMEOUT = _settings.training_job_timeout_seconds  # 7200 by default

# Fast queue — seconds-scale housekeeping + deploy orchestration.
_FAST_FUNCTIONS = [
    ping,
    func(profile_dataset.profile_dataset, timeout=600, max_tries=3),
    func(deploy_model.deploy_model, timeout=600, max_tries=3),
    func(teardown_deployment.teardown_deployment, timeout=120, max_tries=1),
    func(cleanup.cleanup, timeout=300, max_tries=1),
]

# Slow queue — ML workloads that can run for minutes to hours.
_SLOW_FUNCTIONS = [
    func(train_run.train_run, timeout=_TRAIN_TIMEOUT, max_tries=2),
    func(analyze_run.analyze_run, timeout=1800, max_tries=2),
    func(build_package.build_package, timeout=1800, max_tries=2),
]


class FastWorkerSettings:
    functions = _FAST_FUNCTIONS
    cron_jobs: list[Any] = []
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name = FAST_QUEUE
    max_jobs = 8
    retry_jobs = True
    job_timeout = 600


class SlowWorkerSettings:
    functions = _SLOW_FUNCTIONS
    cron_jobs: list[Any] = []
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    queue_name = SLOW_QUEUE
    # Concurrency 2 — each trainer can own a whole core + several GB of
    # RAM. Host resource-limit cap on the worker-slow service sizes this
    # at 4 CPU / 4 G; 2 in flight keeps headroom.
    max_jobs = 2
    retry_jobs = True
    job_timeout = _TRAIN_TIMEOUT


# Backward-compat: dev / single-worker setups run this and get all
# functions on the FAST_QUEUE (enqueue() routes train_run / analyze_run
# / build_package onto SLOW_QUEUE, so a single-worker WorkerSettings will
# not pick those up — production must run the split pair).
class WorkerSettings(FastWorkerSettings):
    functions = _FAST_FUNCTIONS + _SLOW_FUNCTIONS
    queue_name = FAST_QUEUE
    max_jobs = 4
    job_timeout = _TRAIN_TIMEOUT
