"""ASGI middleware that records every prediction.

Queues records async, drains them on a background task that POSTs batches of 50
to ``INTERNAL_INGEST_URL`` with a shared-secret ``X-Internal-Token`` header whose
value must match the backend's ``INTERNAL_HMAC_TOKEN`` setting.
Drop-on-overflow, never blocks the request.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import structlog

logger = structlog.get_logger("serving.predictions")


DEFAULT_URL = "http://api:8000/api/internal/predictions"
BATCH_SIZE = 50
QUEUE_MAXSIZE = 1000


class PredictionLogMiddleware:
    """ASGI middleware capturing per-request prediction telemetry."""

    def __init__(self, app: Any, model_version: str | None = None) -> None:
        self.app = app
        self.model_version = model_version or os.environ.get("MODEL_URI", "unknown")
        self.deployment_id = os.environ.get("DEPLOYMENT_ID", "unknown")
        self.log_url = os.environ.get("INTERNAL_INGEST_URL") or os.environ.get(
            "PREDICTION_LOG_URL", DEFAULT_URL
        )
        self.token = os.environ.get("INTERNAL_HMAC_TOKEN") or os.environ.get(
            "PREDICTION_LOG_TOKEN", ""
        )
        self.audit_payloads = os.environ.get("AUDIT_PAYLOADS", "false").strip().lower() == "true"
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._dropped = 0
        self._started = False
        self._drain_task: asyncio.Task[None] | None = None

    async def _ensure_drain(self) -> None:
        if self._started:
            return
        self._started = True
        self._drain_task = asyncio.create_task(self._drain_loop())

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/predict"):
            await self.app(scope, receive, send)
            return

        await self._ensure_drain()

        trace_id = str(uuid.uuid4())
        start = time.monotonic()

        # Capture request body only when audit is on; else we count length only.
        request_body = bytearray()
        request_body_len = 0

        async def wrapped_receive() -> dict[str, Any]:
            nonlocal request_body_len
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                request_body_len += len(body)
                if self.audit_payloads:
                    request_body.extend(body)
            return message

        status_holder: dict[str, Any] = {"status": 500}
        response_body = bytearray()
        response_body_len = 0

        async def wrapped_send(message: dict[str, Any]) -> None:
            nonlocal response_body_len
            if message.get("type") == "http.response.start":
                status_holder["status"] = message.get("status", 500)
                headers = list(message.get("headers", []))
                headers.append((b"x-trace-id", trace_id.encode()))
                message = {**message, "headers": headers}
            elif message.get("type") == "http.response.body":
                body = message.get("body", b"")
                response_body_len += len(body)
                if self.audit_payloads:
                    response_body.extend(body)
            await send(message)

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        finally:
            latency_ms = (time.monotonic() - start) * 1000
            mode = "batch" if path.endswith("/batch") else "online"
            input_preview: dict[str, Any] | None = None
            output_preview: dict[str, Any] | None = None
            if self.audit_payloads:
                try:
                    input_preview = {"body": request_body.decode(errors="replace")[:8192]}
                    output_preview = {"body": response_body.decode(errors="replace")[:8192]}
                except Exception:
                    input_preview = None
                    output_preview = None
            record = {
                "deployment_id": self.deployment_id,
                "received_at": datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(),
                "latency_ms": round(latency_ms, 2),
                "mode": mode,
                "status_code": status_holder["status"],
                "trace_id": trace_id,
                "input_preview_json": input_preview or {"bytes": request_body_len},
                "output_preview_json": output_preview or {"bytes": response_body_len},
            }

            try:
                self._queue.put_nowait(record)
            except asyncio.QueueFull:
                self._dropped += 1
                logger.warning("prediction_log.dropped", dropped_total=self._dropped)

    async def _drain_loop(self) -> None:
        while True:
            try:
                batch = [await self._queue.get()]
                while len(batch) < BATCH_SIZE:
                    try:
                        batch.append(self._queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                await self._post_batch(batch)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("prediction_log.drain_error", error=str(exc))
                await asyncio.sleep(1.0)

    async def _post_batch(self, batch: list[dict[str, Any]]) -> None:
        # Use stdlib urllib to avoid pulling httpx into the serving base image.
        import urllib.request

        body = json.dumps({"items": batch}, default=str).encode("utf-8")

        req = urllib.request.Request(
            self.log_url,
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                "x-internal-token": self.token,
                "x-deployment-id": self.deployment_id,
            },
        )
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=5).read())  # noqa: S310 — trusted internal URL
        except Exception as exc:
            logger.warning("prediction_log.post_failed", error=str(exc), batch_size=len(batch))


__all__ = ["PredictionLogMiddleware"]
