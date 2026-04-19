from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import delete

from aipacken.config import get_settings
from aipacken.db.models import Artifact, Prediction

logger = structlog.get_logger(__name__)


async def cleanup(ctx: dict[str, Any]) -> dict[str, Any]:
    session_factory = ctx["session_factory"]
    settings = get_settings()

    cutoff_preds = datetime.now(timezone.utc) - timedelta(days=settings.prediction_retention_days)
    cutoff_arts = datetime.now(timezone.utc) - timedelta(days=settings.artifact_retention_days)

    async with session_factory() as db:
        pred_deleted = (
            await db.execute(delete(Prediction).where(Prediction.received_at < cutoff_preds))
        ).rowcount
        art_deleted = (
            await db.execute(delete(Artifact).where(Artifact.created_at < cutoff_arts))
        ).rowcount
        await db.commit()

    try:
        import docker

        client = docker.from_env()
        client.images.prune(filters={"dangling": True})
    except Exception as exc:
        logger.warning("cleanup.docker_prune_failed", error=str(exc))

    return {
        "predictions_deleted": int(pred_deleted or 0),
        "artifacts_deleted": int(art_deleted or 0),
    }
