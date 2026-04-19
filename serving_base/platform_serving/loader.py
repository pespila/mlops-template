"""MLflow model loader — wraps mlflow.pyfunc.load_model + schema inference."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mlflow.pyfunc  # type: ignore[import-not-found]


def _find_input_schema(local_model_path: Path) -> dict[str, Any]:
    """Locate ``input_schema.json`` inside a downloaded model directory.

    MLflow stores pyfunc model artifacts under ``<root>/artifacts/``; sklearn
    models store custom files alongside ``MLmodel``. We search both.
    """
    candidates = [
        local_model_path / "input_schema.json",
        local_model_path / "artifacts" / "input_schema.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return json.loads(candidate.read_text())

    # Deep search as a last resort.
    for found in local_model_path.rglob("input_schema.json"):
        return json.loads(found.read_text())

    return {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
        "title": "ModelInput",
    }


def _output_schema_from_model(model: Any) -> dict[str, Any]:
    """Best-effort output schema derivation from the MLflow signature."""
    try:
        metadata = model.metadata
        signature = metadata.signature if metadata else None
        if signature and signature.outputs:
            cols = signature.outputs.to_dict()
            return {"type": "object", "properties": {str(c.get("name", "output")): {"type": "string"} for c in cols}}
    except Exception:
        pass
    return {"type": "object", "properties": {"prediction": {}}, "additionalProperties": True}


def load(mlflow_uri: str) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Load the model at *mlflow_uri*. Returns (pyfunc_model, input_schema, output_schema)."""
    if not mlflow_uri:
        raise RuntimeError("MODEL_URI is empty — serving container cannot start")

    model = mlflow.pyfunc.load_model(mlflow_uri)

    local_path: Path
    try:
        # Newer MLflow exposes _model_meta.artifact_path; older has .metadata.
        local_path = Path(model._model_impl.context.artifacts.get("__root__", "."))  # type: ignore[attr-defined]
    except Exception:
        local_path = Path(".")

    # mlflow.pyfunc.load_model downloads artifacts under a tmp dir exposed via model.metadata.
    try:
        from mlflow.artifacts import download_artifacts  # type: ignore[import-not-found]

        local_path = Path(download_artifacts(artifact_uri=mlflow_uri))
    except Exception:
        pass

    input_schema = _find_input_schema(local_path)
    output_schema = _output_schema_from_model(model)
    return model, input_schema, output_schema


__all__ = ["load"]
