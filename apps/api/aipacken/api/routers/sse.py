from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from aipacken.db.models import User
from aipacken.services.auth import get_current_user
from aipacken.services.redis_client import get_redis

router = APIRouter(tags=["sse"])


def _shape_log(raw: Any) -> dict[str, Any]:
    """Normalize a raw redis payload into a {ts, level, message} log record."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return {
                        "ts": str(parsed.get("ts") or datetime.now(timezone.utc).isoformat()),
                        "level": str(parsed.get("level") or "info"),
                        "message": str(parsed.get("message") or parsed.get("msg") or stripped),
                    }
            except json.JSONDecodeError:
                pass
        level = "error" if "ERROR" in raw.upper() else ("warn" if "WARN" in raw.upper() else "info")
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": raw,
        }
    if isinstance(raw, dict):
        return {
            "ts": str(raw.get("ts") or datetime.now(timezone.utc).isoformat()),
            "level": str(raw.get("level") or "info"),
            "message": str(raw.get("message") or raw.get("msg") or json.dumps(raw)),
        }
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": "info",
        "message": str(raw),
    }


async def _subscribe(channel: str, event_name: str = "log") -> AsyncIterator[str]:
    r = get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    try:
        yield "retry: 5000\n\n"
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
            if msg is None:
                yield ": keepalive\n\n"
                continue
            record = _shape_log(msg.get("data"))
            payload = json.dumps(record, default=str)
            yield f"event: {event_name}\ndata: {payload}\n\n"
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


def _stream(channel: str, event_name: str = "log") -> StreamingResponse:
    async def gen() -> AsyncIterator[bytes]:
        async for line in _subscribe(channel, event_name):
            yield line.encode("utf-8")
            await asyncio.sleep(0)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/logs")
async def stream_run_logs(run_id: str, user: User = Depends(get_current_user)) -> StreamingResponse:
    return _stream(f"run:{run_id}:logs")


@router.get("/runs/{run_id}/metrics")
async def stream_run_metrics(run_id: str, user: User = Depends(get_current_user)) -> StreamingResponse:
    return _stream(f"run:{run_id}:metrics", event_name="metric")


@router.get("/deployments/{deployment_id}/events")
async def stream_deployment_events(
    deployment_id: str, user: User = Depends(get_current_user)
) -> StreamingResponse:
    return _stream(f"deployment:{deployment_id}:events")


@router.get("/datasets/{dataset_id}/status")
async def stream_dataset_status(
    dataset_id: str, user: User = Depends(get_current_user)
) -> StreamingResponse:
    return _stream(f"dataset:{dataset_id}:status")
