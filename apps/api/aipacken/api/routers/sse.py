from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from aipacken.db.models import User
from aipacken.services.auth import get_current_user
from aipacken.services.redis_client import get_redis

router = APIRouter(tags=["sse"])


async def _subscribe(channel: str) -> AsyncIterator[str]:
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
            data = msg.get("data")
            if isinstance(data, (bytes, bytearray)):
                data = data.decode("utf-8", errors="replace")
            if isinstance(data, (dict, list)):
                data = json.dumps(data)
            yield f"data: {data}\n\n"
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


def _stream(channel: str) -> StreamingResponse:
    async def gen() -> AsyncIterator[bytes]:
        async for line in _subscribe(channel):
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
    return _stream(f"run:{run_id}:metrics")


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
