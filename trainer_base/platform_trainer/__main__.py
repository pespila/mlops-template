"""Training-container entrypoint.

Reads configuration from env vars set by the platform worker:

    RUN_ID             platform Run id (also MLFLOW_RUN_ID in most setups)
    DATASET_URI        s3://... or pre-signed HTTP(S) URL
    TRANSFORM_CONFIG   JSON: {target, transforms[], split{}}
    MODEL_CATALOG      JSON: {kind, hyperparams, time_limit?, presets?}
    SENSITIVE_FEATURES JSON: list[str] (may be empty)
    MLFLOW_TRACKING_URI, MLFLOW_EXPERIMENT_ID, MLFLOW_RUN_ID
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_ENDPOINT_URL
    ARTIFACT_BUCKET    s3 bucket for SHAP/bias PNG uploads

Exit code: 0 on success, 1 on failure.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from platform_trainer import analyze, io as io_mod, mlflow_sink, transforms
from platform_trainer.adapters import get_adapter


logger = logging.getLogger("platform_trainer")


class _JsonFormatter(logging.Formatter):
    """Minimal JSON formatter — avoids an extra structlog dependency."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in logging.LogRecord("", 0, "", 0, "", None, None).__dict__
            and k != "message"
        }
        if extras:
            payload.update(extras)
        return json.dumps(payload, default=str)


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"missing required env var: {name}")
    return val or ""


def _maybe_upload(local: Path, kind: str) -> str | None:
    bucket = os.environ.get("ARTIFACT_BUCKET")
    run_id = os.environ.get("RUN_ID") or "unknown"
    if not bucket or not local.exists():
        return None
    s3_uri = f"s3://{bucket}/runs/{run_id}/{kind}/{local.name}"
    try:
        io_mod.upload_artifact(local, s3_uri)
        return s3_uri
    except Exception as exc:
        logger.warning("artifact.upload_failed", extra={"uri": s3_uri, "error": str(exc)})
        return None


def _feature_names(preprocessor: Any, fallback: list[str]) -> list[str]:
    try:
        names = preprocessor.get_feature_names_out()
        return [str(n) for n in names]
    except Exception:
        return fallback


def main() -> int:
    _configure_logging()
    t_start = time.monotonic()
    run_id = _env("RUN_ID", required=True)
    logger.info("trainer.start", extra={"run_id": run_id})

    try:
        transform_cfg = io_mod.read_json_env("TRANSFORM_CONFIG")
        model_catalog = io_mod.read_json_env("MODEL_CATALOG")
        sensitive_features = io_mod.read_json_env("SENSITIVE_FEATURES") or []
        if not isinstance(sensitive_features, list):
            raise ValueError("SENSITIVE_FEATURES must be a JSON list")

        dataset_uri = _env("DATASET_URI", required=True)
        target = transform_cfg.get("target")
        if not target:
            raise ValueError("TRANSFORM_CONFIG.target is required")

        work_dir = Path("/tmp/trainer")
        work_dir.mkdir(parents=True, exist_ok=True)

        # Pass the directory — io_mod preserves the remote filename extension
        # (suffix is load-bearing: parse_dataset dispatches on it).
        dataset_path = io_mod.download_dataset(dataset_uri, work_dir)
        logger.info("dataset.downloaded", extra={"path": str(dataset_path)})

        df = io_mod.parse_dataset(dataset_path)
        if target not in df.columns:
            raise ValueError(f"target column {target!r} not in dataset")

        task = transforms.infer_task(df[target])
        logger.info("task.inferred", extra={"task": task, "rows": len(df)})

        # Auto label-encode non-numeric classification targets so every adapter
        # (XGBoost/LightGBM/AutoGluon/sklearn) sees numeric y. Encoder is
        # preserved and logged so serving can inverse_transform the prediction.
        target_label_encoder = None
        target_classes: list[str] | None = None
        if task == "classification":
            y_series = df[target]
            import pandas as _pd

            if not _pd.api.types.is_numeric_dtype(y_series) or _pd.api.types.is_bool_dtype(y_series):
                from sklearn.preprocessing import LabelEncoder

                target_label_encoder = LabelEncoder().fit(y_series)
                df[target] = target_label_encoder.transform(y_series)
                target_classes = [str(c) for c in target_label_encoder.classes_]
                logger.info(
                    "target.label_encoded",
                    extra={"classes": target_classes, "n": len(target_classes)},
                )

        X_train, X_val, X_test, y_train, y_val, y_test = transforms.apply_split(
            df, target=target, split_config=transform_cfg.get("split") or {}, task=task,
        )

        schema = transforms.coarse_schema(df.drop(columns=[target]))
        preprocessor, kept_cols = transforms.build_column_transformer(
            transforms=transform_cfg.get("transforms") or [],
            schema=schema,
        )

        kind = (model_catalog.get("kind") or "").strip()
        hyperparams = model_catalog.get("hyperparams") or {}
        time_limit = int(model_catalog.get("time_limit") or 0) or None
        presets = model_catalog.get("presets") or "medium_quality"

        adapter = get_adapter(kind)

        model: Any
        metrics: dict[str, Any]
        flavor: str
        feature_names: list[str]
        X_post_sample: Any
        signature: Any = None
        input_example: Any = None

        if kind == "autogluon":
            train_df = X_train.copy()
            train_df[target] = y_train.values
            val_df = X_val.copy()
            val_df[target] = y_val.values
            predictor_path = work_dir / "autogluon"
            model, metrics = adapter.fit(
                train_df=train_df,
                val_df=val_df,
                target=target,
                hyperparams=hyperparams,
                task=task,
                time_limit=time_limit,
                presets=presets,
                output_dir=predictor_path,
            )
            flavor = "autogluon"
            feature_names = list(X_train.columns)
            X_post_sample = X_val
            input_example = X_val.head(5)

            y_pred = model.predict(X_val)
        else:
            model, metrics = adapter.fit(
                kind=kind,
                X_train=X_train,
                y_train=y_train,
                X_val=X_val,
                y_val=y_val,
                hyperparams=hyperparams,
                task=task,
                preprocessor=preprocessor,
            )
            flavor = "sklearn"
            pre_fitted = model.named_steps["preprocess"]
            feature_names = _feature_names(pre_fitted, kept_cols)
            X_post_sample = pre_fitted.transform(X_val)
            input_example = X_val.head(5)

            try:
                from mlflow.models.signature import infer_signature

                signature = infer_signature(X_val.head(50), model.predict(X_val.head(50)))
            except Exception:
                signature = None
            y_pred = model.predict(X_val)

        logger.info(
            "train.complete",
            extra={"metrics": {k: v for k, v in metrics.items() if not isinstance(v, (list, dict))}},
        )

        shap_report: dict[str, Any] = {}
        try:
            sample_n = min(200, len(X_val))
            shap_report = analyze.compute_shap(
                model=model,
                X_sample=X_val.head(sample_n),
                feature_names=feature_names,
            )
        except Exception as exc:
            logger.warning("shap.failed", extra={"error": str(exc)})

        bias_report: dict[str, Any] = {}
        if sensitive_features:
            present = [c for c in sensitive_features if c in X_val.columns]
            if present:
                try:
                    bias_report = analyze.compute_bias(
                        y_true=y_val,
                        y_pred=y_pred,
                        sensitive_df=X_val[present],
                        metric="accuracy" if task == "classification" else "mae",
                    )
                except Exception as exc:
                    logger.warning("bias.failed", extra={"error": str(exc)})
            else:
                logger.info(
                    "bias.skipped",
                    extra={"reason": "sensitive features not in feature frame"},
                )

        shap_uri = _maybe_upload(Path("/tmp/shap_global.png"), "shap")
        bias_uri = _maybe_upload(Path("/tmp/bias.png"), "bias")

        # Log JSON payloads for the frontend SHAP bar chart + bias table.
        # log_dict is a single REST call to MLflow — no dep on flask.
        try:
            import mlflow as _mlflow

            tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
            if tracking_uri:
                _mlflow.set_tracking_uri(tracking_uri)
            active = _mlflow.active_run()
            mlflow_run_id_env = os.environ.get("MLFLOW_RUN_ID") or run_id
            _ctx = _mlflow.start_run(run_id=mlflow_run_id_env) if active is None else None
            try:
                if shap_report:
                    payload = {
                        "global_importance": shap_report.get("global_importance", {}),
                    }
                    _mlflow.log_dict(payload, "shap_report.json")
                if bias_report:
                    _mlflow.log_dict(bias_report, "bias_report.json")
            finally:
                if _ctx is not None:
                    _mlflow.end_run()
        except Exception as exc:
            logger.warning("mlflow.log_reports_failed", extra={"error": str(exc)})

        input_schema = mlflow_sink.build_input_schema(X_post_sample, feature_names)
        artifacts_dir = work_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        if shap_report.get("global_importance"):
            (artifacts_dir / "shap_global_importance.json").write_text(
                json.dumps(shap_report["global_importance"], indent=2)
            )
        if bias_report:
            (artifacts_dir / "bias_report.json").write_text(json.dumps(bias_report, indent=2, default=str))

        params_to_log: dict[str, Any] = {
            "model_kind": kind,
            "task": task,
            "target": target,
            "n_train": int(len(X_train)),
            "n_val": int(len(X_val)),
            "n_test": int(len(X_test)),
            "hyperparams": hyperparams,
        }

        logged_run_id = mlflow_sink.log_run(
            run_id=os.environ.get("MLFLOW_RUN_ID") or "",
            params=params_to_log,
            metrics=metrics,
            artifacts_dir=artifacts_dir,
            model=model,
            signature=signature,
            flavor=flavor,
            input_example=input_example,
            input_schema=input_schema,
        )

        duration = time.monotonic() - t_start
        logger.info(
            "trainer.complete",
            extra={
                "run_id": run_id,
                "mlflow_run_id": logged_run_id,
                "duration_sec": round(duration, 2),
                "shap_uri": shap_uri,
                "bias_uri": bias_uri,
            },
        )
        return 0
    except Exception as exc:
        logger.error(
            "trainer.failed",
            extra={"run_id": run_id, "error": str(exc), "trace": traceback.format_exc()},
        )
        raise


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(1)
