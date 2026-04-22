"""Minimal Redis-backed fixed-window rate limiter.

Hot endpoints (login, predict, upload, run creation) get a per-user (or
per-IP when unauthenticated) counter that INCRs on each request and expires
after ``window_seconds``. A ``too_many_requests`` 429 is returned the moment
the counter crosses the configured ceiling.

Deliberately tiny — no new deps, no token-bucket math, no burst allowance.
At the scale of a self-hosted MLOps platform a fixed-window is what's
warranted; upgrade to slowapi or an edge-level rate-limit middleware in
Traefik when operations demand it.

Closes security.md P1 "No rate limiting anywhere".
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request

from aipacken.services.redis_client import get_redis


@dataclass(frozen=True, slots=True)
class RateLimit:
    """A (limit, window_seconds) pair. Name is the Redis-key prefix."""

    name: str
    limit: int
    window_seconds: int


def _identity(req: Request) -> str:
    """Prefer the authenticated user id; fall back to client IP."""
    user_id = req.session.get("user_id") if hasattr(req, "session") else None
    if user_id:
        return f"u:{user_id}"
    client = req.client
    return f"ip:{client.host if client else 'unknown'}"


def rate_limit(rule: RateLimit) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency that enforces ``rule`` before the handler runs."""

    async def _enforce(request: Request) -> None:
        redis = get_redis()
        # Bucket key floors the wall-clock into window_seconds-sized slots
        # so every request in the same window maps to the same key. On the
        # first hit the key does not exist (INCR returns 1) and we stamp an
        # EXPIRE so we don't leak unbounded keys into Redis.
        now = int(time.time())
        bucket = now // rule.window_seconds
        key = f"ratelimit:{rule.name}:{_identity(request)}:{bucket}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, rule.window_seconds)
        if count > rule.limit:
            retry_after = rule.window_seconds - (now % rule.window_seconds)
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "rule": rule.name,
                    "limit": rule.limit,
                    "window_seconds": rule.window_seconds,
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

    return _enforce


# Per-endpoint limits tuned for a self-hosted single-tenant appliance. Raise
# them via env-var overrides once observability shows headroom.
LOGIN_LIMIT = RateLimit(name="auth_login", limit=10, window_seconds=60)
PREDICT_LIMIT = RateLimit(name="predict", limit=600, window_seconds=60)
UPLOAD_LIMIT = RateLimit(name="dataset_upload", limit=30, window_seconds=300)
RUN_CREATE_LIMIT = RateLimit(name="run_create", limit=60, window_seconds=300)
