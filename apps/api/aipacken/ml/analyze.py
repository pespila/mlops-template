"""SHAP + fairness hooks.

Historically created placeholder DB rows for ExplanationArtifact and
BiasReport. Both tables were dropped in migration 0007_mlflow_a — the
trainer container emits ``reports/shap.json`` + ``reports/bias.json``
under its MLflow run and the UI reads them through
``aipacken.services.mlflow_client.read_run_json``.

Kept as an import-compat shim so nothing that still imports this module
at load time breaks. If you find yourself needing a real implementation
here, the right place is almost certainly the trainer.
"""

from __future__ import annotations

from typing import Any

from aipacken.db.models import Run


async def compute_shap_and_bias(_db: Any, _run: Run) -> dict[str, Any]:
    """No-op. See module docstring."""
    return {"shap_id": None, "bias_id": None}
