from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from aipacken.config import get_settings
from aipacken.db.models import Deployment, ModelVersion
from aipacken.docker_client.builder_client import get_builder_client
from aipacken.services.redis_client import publish

logger = structlog.get_logger(__name__)


async def deploy_model(ctx: dict[str, Any], deployment_id: str) -> dict[str, Any]:
    session_factory = ctx["session_factory"]
    settings = get_settings()

    async with session_factory() as db:
        dep = await db.get(Deployment, deployment_id)
        if dep is None:
            return {"status": "missing"}
        mv = await db.get(ModelVersion, dep.model_version_id)
        if mv is None:
            dep.status = "failed"
            await db.commit()
            return {"status": "failed", "reason": "model_version_missing"}

        dep.status = "deploying"
        await db.commit()
        await publish(f"deployment:{deployment_id}:events", {"status": "deploying"})

        image = mv.serving_image_uri or settings.serving_base_image
        env = {
            "MODEL_URI": f"models:/{mv.registered_model_id}/{mv.mlflow_version or 'latest'}",
            "MLFLOW_TRACKING_URI": settings.mlflow_tracking_uri,
            "S3_ENDPOINT_URL": settings.s3_endpoint_url,
            "AWS_ACCESS_KEY_ID": settings.minio_root_user,
            "AWS_SECRET_ACCESS_KEY": settings.minio_root_password,
            "DEPLOYMENT_ID": dep.id,
            "INTERNAL_INGEST_URL": "http://api:8000/api/internal/predictions",
            "INTERNAL_HMAC_TOKEN": settings.internal_hmac_token,
        }
        labels = {
            "platform.deployment_id": dep.id,
            "traefik.enable": "true",
            f"traefik.http.routers.model-{dep.slug}.rule": f"PathPrefix(`/models/{dep.slug}`)",
            f"traefik.http.routers.model-{dep.slug}.entrypoints": "web",
            f"traefik.http.services.model-{dep.slug}.loadbalancer.server.port": "8000",
            "traefik.docker.network": settings.models_network,
        }

        builder = get_builder_client()
        try:
            res = await builder.run(
                image=image,
                env=env,
                memory_bytes=2 * 1024 * 1024 * 1024,
                nano_cpus=1_000_000_000,
                network=settings.models_network,
                labels=labels,
            )
        except Exception as exc:
            logger.exception("deploy_model.run_failed")
            dep.status = "failed"
            await db.commit()
            return {"status": "failed", "error": str(exc)}

        container_id = res["container_id"]
        internal_url = f"http://model-{dep.slug}:8000"

        ready = False
        async with httpx.AsyncClient(timeout=5.0) as client:
            for _ in range(30):
                try:
                    r = await client.get(f"{internal_url}/ready")
                    if r.status_code == 200:
                        ready = True
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(2)

        dep.container_id = container_id
        dep.internal_url = internal_url
        dep.endpoint_url = f"/models/{dep.slug}"
        dep.status = "active" if ready else "unhealthy"
        dep.last_health_at = datetime.now(timezone.utc)
        await db.commit()
        await publish(f"deployment:{deployment_id}:events", {"status": dep.status})
        return {"status": dep.status, "container_id": container_id}
