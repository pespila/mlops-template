from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from aipacken.db.models import Run
from aipacken.services.redis_client import publish

logger = structlog.get_logger(__name__)


async def analyze_run(ctx: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Post-training SHAP + fairlearn analysis.

    The heavy lifting (model load, SHAP sampling, fairlearn metric frames,
    PNG uploads, DB rows) is delegated to `aipacken.ml.analyze` which is
    shared with the training container. This wrapper is the Arq entrypoint.
    """
    session_factory = ctx["session_factory"]

    async with session_factory() as db:
        run = await db.get(Run, run_id)
        if run is None:
            return {"status": "missing"}

        try:
            from aipacken.ml import analyze as ml_analyze  # imported lazily — avoids heavy deps at worker boot

            await ml_analyze.compute_shap_and_bias(db, run)
        except Exception as exc:
            logger.exception("analyze_run.failed")
            run.status = "failed"
            run.error_message = f"analyze: {exc}"
            run.finished_at = datetime.now(timezone.utc)
            await db.commit()
            await publish(f"run:{run_id}:logs", f"ANALYZE_ERROR: {exc}")
            return {"status": "failed", "error": str(exc)}

        run.status = "succeeded"
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()
        await publish(f"run:{run_id}:logs", "ANALYZE_COMPLETE")
        return {"status": "succeeded", "run_id": run_id}
