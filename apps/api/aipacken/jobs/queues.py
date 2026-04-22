"""Queue name constants + the function-to-queue routing table.

Split out of ``worker.py`` / ``queue.py`` to avoid a circular import —
the worker needs to declare per-function timeouts, and the queue
producer needs to route enqueues to the right queue; both need the
queue names.
"""

from __future__ import annotations

# Redis list keys used by arq to dispatch jobs. The `FastWorkerSettings`
# and `SlowWorkerSettings` classes in ``aipacken.jobs.worker`` subscribe
# to these.
FAST_QUEUE = "platform:fast"
SLOW_QUEUE = "platform:slow"


# Explicit allowlist: every job function name maps to exactly one queue.
# Anything missing falls back to FAST_QUEUE in ``enqueue()``.
QUEUE_FOR_FUNCTION: dict[str, str] = {
    "ping": FAST_QUEUE,
    "profile_dataset": FAST_QUEUE,
    "deploy_model": FAST_QUEUE,
    "teardown_deployment": FAST_QUEUE,
    "cleanup": FAST_QUEUE,
    "train_run": SLOW_QUEUE,
    "analyze_run": SLOW_QUEUE,
    "build_package": SLOW_QUEUE,
}
