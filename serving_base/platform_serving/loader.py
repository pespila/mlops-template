"""Model loader — reads a model from the bind-mounted platform-data volume."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _resolve_storage_path() -> Path:
    data_root = Path(os.environ.get("DATA_ROOT", "/var/platform-data"))
    rel = os.environ.get("MODEL_STORAGE_PATH", "")
    if not rel:
        raise RuntimeError("MODEL_STORAGE_PATH is empty — serving container cannot start")
    return data_root / rel


def _find_input_schema(model_dir: Path) -> dict[str, Any]:
    """Look for input_schema.json next to the model artifact."""
    search_roots = [model_dir, model_dir.parent]
    for root in search_roots:
        for found in root.rglob("input_schema.json"):
            try:
                return json.loads(found.read_text())
            except Exception:
                continue
    return {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
        "title": "ModelInput",
    }


def load(_legacy_uri: str = "") -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Load the model located at MODEL_STORAGE_PATH.

    Returns (model, input_schema, output_schema). `_legacy_uri` is accepted for
    signature compatibility with the previous MLflow-based loader but is
    ignored.
    """
    path = _resolve_storage_path()
    kind = (os.environ.get("MODEL_KIND") or "sklearn").lower()

    if kind == "autogluon" or path.is_dir():
        from autogluon.tabular import TabularPredictor  # type: ignore[import-not-found]

        predictor_dir = path if path.is_dir() else path.parent
        model = TabularPredictor.load(str(predictor_dir))
        schema_dir = predictor_dir
    else:
        import joblib

        if not path.exists():
            raise RuntimeError(f"model artifact not found at {path}")
        model = joblib.load(path)
        schema_dir = path.parent

    input_schema = _find_input_schema(schema_dir)
    output_schema = {
        "type": "object",
        "properties": {"prediction": {}},
        "additionalProperties": True,
    }
    return model, input_schema, output_schema


__all__ = ["load"]
