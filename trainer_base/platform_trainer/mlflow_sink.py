"""MLflow logging helpers for both sklearn pipelines and AutoGluon predictors."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

# mlflow-skinny exposes everything we need for the happy path.
import mlflow


class AutoGluonPyFuncWrapper(mlflow.pyfunc.PythonModel):  # type: ignore[misc]
    """PyFunc wrapper around a serialized AutoGluon ``TabularPredictor``.

    ``context.artifacts['predictor']`` must be the directory where
    ``TabularPredictor.save()`` wrote its contents.
    """

    def load_context(self, context: Any) -> None:
        from autogluon.tabular import TabularPredictor  # type: ignore[import-not-found]

        self._predictor = TabularPredictor.load(context.artifacts["predictor"])

    def predict(self, context: Any, model_input: Any) -> Any:  # noqa: ARG002
        if not isinstance(model_input, pd.DataFrame):
            model_input = pd.DataFrame(model_input)
        return self._predictor.predict(model_input)


def _dtype_to_json_schema(dtype: Any) -> dict[str, Any]:
    name = str(dtype).lower()
    if "bool" in name:
        return {"type": "boolean"}
    if "int" in name:
        return {"type": "integer"}
    if "float" in name or "double" in name or "number" in name:
        return {"type": "number"}
    if "datetime" in name or "date" in name:
        return {"type": "string", "format": "date-time"}
    return {"type": "string"}


def build_input_schema(X_post: Any, feature_names: list[str]) -> dict[str, Any]:
    """Build a JSON-Schema object describing the post-transform feature vector."""
    if hasattr(X_post, "dtypes"):
        dtypes = {str(col): X_post.dtypes[col] for col in X_post.columns}
    else:
        # ndarray — assume float unless sentinel integer columns are detected.
        import numpy as np

        arr = X_post if hasattr(X_post, "dtype") else np.asarray(X_post)
        kind = arr.dtype.kind
        common = "integer" if kind in ("i", "u") else "number" if kind == "f" else "string"
        dtypes = {name: common for name in feature_names}

    properties: dict[str, Any] = {}
    for name in feature_names:
        d = dtypes.get(name, "number")
        properties[name] = _dtype_to_json_schema(d) if not isinstance(d, str) else {"type": d}

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ModelInput",
        "type": "object",
        "properties": properties,
        "required": list(feature_names),
        "additionalProperties": False,
    }


def _log_artifact_safe(path: Path) -> None:
    if path.exists():
        mlflow.log_artifact(str(path))


def log_run(
    run_id: str,
    params: dict[str, Any],
    metrics: dict[str, Any],
    artifacts_dir: Path,
    model: Any,
    signature: Any,
    flavor: str,
    input_example: Any | None = None,
    input_schema: dict[str, Any] | None = None,
    registered_model_name: str | None = None,
) -> str:
    """Log params, scalar metrics, artifacts and the model. Returns the MLflow run id."""

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    experiment_id = os.environ.get("MLFLOW_EXPERIMENT_ID")
    active = mlflow.active_run()
    ctx = (
        mlflow.start_run(run_id=run_id) if run_id else mlflow.start_run(experiment_id=experiment_id)
    ) if active is None else None

    try:
        mlflow.log_params({k: _scalarize(v) for k, v in (params or {}).items()})

        scalar_metrics = {k: float(v) for k, v in (metrics or {}).items() if _is_scalar(v)}
        if scalar_metrics:
            mlflow.log_metrics(scalar_metrics)

        artifacts_dir.mkdir(parents=True, exist_ok=True)

        if input_schema is not None:
            schema_path = artifacts_dir / "input_schema.json"
            schema_path.write_text(json.dumps(input_schema, indent=2))
            _log_artifact_safe(schema_path)

        # Best-effort log of leaderboard + nested tables emitted by AutoGluon.
        for key in ("leaderboard",):
            if key in (metrics or {}):
                table_path = artifacts_dir / f"{key}.json"
                table_path.write_text(json.dumps(metrics[key], indent=2, default=str))
                _log_artifact_safe(table_path)

        for extra in ("/tmp/shap_global.png", "/tmp/bias.png"):
            _log_artifact_safe(Path(extra))

        if flavor == "sklearn":
            try:
                import mlflow.sklearn as mlflow_sklearn  # type: ignore[import-not-found]

                # Skip input_example — MLflow's validate-serving-input path
                # pulls in `flask`, which our slim trainer image doesn't have.
                mlflow_sklearn.log_model(
                    sk_model=model,
                    artifact_path="model",
                    signature=signature,
                    registered_model_name=registered_model_name,
                )
            except ImportError:
                # mlflow-skinny fallback: pickle the estimator and wrap in pyfunc.
                import pickle

                pkl = artifacts_dir / "sklearn_model.pkl"
                with pkl.open("wb") as fh:
                    pickle.dump(model, fh)

                class _SklearnPyFunc(mlflow.pyfunc.PythonModel):
                    def load_context(self, context: Any) -> None:  # noqa: D401
                        with open(context.artifacts["pickle"], "rb") as fh:
                            self._model = pickle.load(fh)  # noqa: S301 — our own pickle

                    def predict(self, context: Any, model_input: Any) -> Any:  # noqa: ARG002
                        return self._model.predict(model_input)

                mlflow.pyfunc.log_model(
                    artifact_path="model",
                    python_model=_SklearnPyFunc(),
                    artifacts={"pickle": str(pkl)},
                    signature=signature,
                    registered_model_name=registered_model_name,
                )
        elif flavor == "autogluon":
            predictor_path = artifacts_dir / "autogluon_predictor"
            model.save(str(predictor_path))
            mlflow.pyfunc.log_model(
                artifact_path="model",
                python_model=AutoGluonPyFuncWrapper(),
                artifacts={"predictor": str(predictor_path)},
                signature=signature,
                registered_model_name=registered_model_name,
            )
        else:
            raise ValueError(f"unknown mlflow flavor: {flavor!r}")

        active = mlflow.active_run()
        return active.info.run_id if active else run_id
    finally:
        if ctx is not None:
            mlflow.end_run()


def _is_scalar(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _scalarize(v: Any) -> Any:
    if isinstance(v, (dict, list, tuple)):
        return json.dumps(v, default=str)
    return v


__all__ = ["AutoGluonPyFuncWrapper", "build_input_schema", "log_run"]
