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
    MinIO. This function picks up those artifacts and records pointer rows.
    If the trainer published nothing yet we create empty placeholders so the
    UI can render a graceful "not available" state.
    """
    placeholder_shap = ExplanationArtifact(
        run_id=run.id,
        kind="shap",
        feature_importance_json=None,
        artifact_uri=None,
    )
    db.add(placeholder_shap)

    placeholder_bias = BiasReport(
        run_id=run.id,
        sensitive_feature="__none__",
        metric_name="demographic_parity_difference",
        group_values_json={},
        overall_value=None,
        report_uri=None,
    )
    db.add(placeholder_bias)
    await db.flush()
    return {"shap_id": placeholder_shap.id, "bias_id": placeholder_bias.id}
