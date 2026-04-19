from __future__ import annotations

from typing import Any

import structlog

from aipacken.db.models import Deployment
from aipacken.docker_client.builder_client import get_builder_client
from aipacken.services.redis_client import publish

logger = structlog.get_logger(__name__)


async def teardown_deployment(ctx: dict[str, Any], deployment_id: str) -> dict[str, Any]:
    session_factory = ctx["session_factory"]
    builder = get_builder_client()

    async with session_factory() as db:
        dep = await db.get(Deployment, deployment_id)
        if dep is None:
            return {"status": "missing"}
        if dep.container_id:
            try:
                await builder.stop(dep.container_id, timeout=10)
            except Exception as exc:
                logger.warning("teardown.stop_failed", error=str(exc))
        dep.status = "stopped"
        dep.container_id = None
        dep.internal_url = None
        await db.commit()
        await publish(f"deployment:{deployment_id}:events", {"status": "stopped"})
        return {"status": "stopped"}
