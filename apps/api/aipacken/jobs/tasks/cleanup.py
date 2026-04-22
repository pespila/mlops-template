from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete

from aipacken.config import get_settings
from aipacken.db.models import Prediction

logger = structlog.get_logger(__name__)


async def cleanup(ctx: dict[str, Any]) -> dict[str, Any]:
    """Retention sweep: prune old predictions + dangling docker images.

    Artifact retention is owned by MLflow now (its artifact store + the
    run lifecycle) — we don't touch that here. Prediction retention stays
    on this side because predictions live in our DB as the audit log.
    """
    session_factory = ctx["session_factory"]
    settings = get_settings()

    cutoff_preds = datetime.now(UTC) - timedelta(days=settings.prediction_retention_days)

    async with session_factory() as db:
        pred_deleted = (
            await db.execute(delete(Prediction).where(Prediction.received_at < cutoff_preds))
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
    }
