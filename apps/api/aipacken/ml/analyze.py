from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.db.models import BiasReport, ExplanationArtifact, Run

logger = structlog.get_logger(__name__)


async def compute_shap_and_bias(db: AsyncSession, run: Run) -> dict[str, Any]:
    """Post-training analysis hook.

    The heavy SHAP + fairlearn computation runs inside the trainer container
    (so it inherits the model's framework) and writes result JSON + PNGs to
    the shared platform-data volume. The train_run worker reads those
    artifacts directly; this function only creates graceful "not available"
    placeholder rows when the trainer published nothing.
    """
    placeholder_shap = ExplanationArtifact(
        run_id=run.id,
        kind="shap",
        feature_importance_json=None,
        artifact_path=None,
    )
    db.add(placeholder_shap)

    placeholder_bias = BiasReport(
        run_id=run.id,
        sensitive_feature="__none__",
        metric_name="demographic_parity_difference",
        group_values_json={},
        overall_value=None,
        report_path=None,
    )
    db.add(placeholder_bias)
    await db.flush()
    return {"shap_id": placeholder_shap.id, "bias_id": placeholder_bias.id}
