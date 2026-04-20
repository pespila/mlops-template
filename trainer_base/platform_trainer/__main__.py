"""Training-container entrypoint.

Reads configuration from env vars set by the platform worker:

    RUN_ID            platform Run id
    DATASET_PATH      absolute path to the raw dataset file (CSV/Parquet/...)
    DATASET_FILENAME  filename only (used to dispatch by extension)
    RUN_DIR           absolute path of /var/platform-data/runs/{run_id}
    TRANSFORM_CONFIG  JSON: {target, transforms[], split{}, sensitive_features[]}
    MODEL_CATALOG     JSON: {kind, hyperparams, time_limit?, presets?}
    SENSITIVE_FEATURES JSON: list[str] (may be empty)

Writes into RUN_DIR:
    metrics.jsonl               one JSON object per line
    artifacts/model.pkl         joblib-dumped pipeline (or autogluon/ dir)
    artifacts/shap_global.png   plot
    artifacts/bias.png          plot
    reports/shap.json           {global_importance, ...}
    reports/bias.json           {metric, groups, deltas, overall}

Exit code: 0 on success, 1 on failure. No network calls, no external SDKs.
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

import pandas as pd

from platform_trainer import analyze, transforms
from platform_trainer.adapters import get_adapter


logger = logging.getLogger("platform_trainer")


class _JsonFormatter(logging.Formatter):
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


def _env(name: str, required: bool = False) -> str:
    val = os.environ.get(name, "")
    if required and not val:
        raise RuntimeError(f"missing required env var: {name}")
    return val


def _read_dataset(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in (".csv", ".tsv"):
        return pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",")
    if suffix in (".parquet", ".pq"):
        return pd.read_parquet(path)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if suffix in (".json", ".jsonl"):
        return pd.read_json(path, lines=suffix == ".jsonl")
    raise ValueError(f"unsupported dataset extension: {suffix!r}")


def _append_metric(path: Path, name: str, value: float, step: int | None = None, phase: str | None = None) -> None:
    row: dict[str, Any] = {"name": name, "value": float(value)}
    if step is not None:
        row["step"] = int(step)
    if phase:
        row["phase"] = phase
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _feature_names(preprocessor: Any, fallback: list[str]) -> list[str]:
    try:
        raw = [str(n) for n in preprocessor.get_feature_names_out()]
    except Exception:
        return fallback
    return [_clean_feature_name(n) for n in raw]


def _clean_feature_name(name: str) -> str:
    """Strip sklearn ColumnTransformer's `<step>__<col>` prefixes.

    ColumnTransformer emits feature names like ``2_standard_scale_age__age``.
    Users care about the underlying column. If a transform expands one input
    into many (one-hot), the expanded suffix after ``__`` is preserved
    (e.g. ``sex__male`` becomes ``sex_male``).
    """
    base = name.split("__", 1)[-1] if "__" in name else name
    # one-hot expansions often come back as `col_value` already; if the
    # remaining half equals the step prefix, drop it.
    return base


def main() -> int:
    _configure_logging()
    t_start = time.monotonic()

    run_id = _env("RUN_ID", required=True)
    run_dir = Path(_env("RUN_DIR", required=True))
    dataset_path = Path(_env("DATASET_PATH", required=True))

    artifacts_dir = run_dir / "artifacts"
    reports_dir = run_dir / "reports"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = run_dir / "metrics.jsonl"

    logger.info("trainer.start", extra={"run_id": run_id, "dataset_path": str(dataset_path)})

    try:
        transform_cfg = json.loads(_env("TRANSFORM_CONFIG") or "{}")
        model_catalog = json.loads(_env("MODEL_CATALOG") or "{}")
        sensitive_features = json.loads(_env("SENSITIVE_FEATURES") or "[]")
        if not isinstance(sensitive_features, list):
            raise ValueError("SENSITIVE_FEATURES must be a JSON list")

        target = transform_cfg.get("target")
        if not target:
            raise ValueError("TRANSFORM_CONFIG.target is required")

        df = _read_dataset(dataset_path)
        if target not in df.columns:
            raise ValueError(f"target column {target!r} not in dataset")

        task = transforms.infer_task(df[target])
        logger.info("task.inferred", extra={"task": task, "rows": len(df)})

        # Auto label-encode non-numeric classification targets so every adapter
        # (XGBoost/LightGBM/AutoGluon/sklearn) sees numeric y.
        target_classes: list[str] | None = None
        if task == "classification":
            y_series = df[target]
            if not pd.api.types.is_numeric_dtype(y_series) or pd.api.types.is_bool_dtype(y_series):
                from sklearn.preprocessing import LabelEncoder

                target_label_encoder = LabelEncoder().fit(y_series)
                df[target] = target_label_encoder.transform(y_series)
                target_classes = [str(c) for c in target_label_encoder.classes_]
                logger.info(
                    "target.label_encoded",
                    extra={"classes": target_classes, "n": len(target_classes)},
                )

        X_train, X_val, X_test, y_train, y_val, y_test = transforms.apply_split(
            df,
            target=target,
            split_config=transform_cfg.get("split") or {},
            task=task,
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
        feature_names: list[str]
        flavor: str

        if kind == "autogluon":
            train_df = X_train.copy()
            train_df[target] = y_train.values
            val_df = X_val.copy()
            val_df[target] = y_val.values
            predictor_path = artifacts_dir / "autogluon"
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
            y_pred = model.predict(X_val)

            # Persist the fitted pipeline (preprocessor + estimator) for serving.
            import joblib

            joblib.dump(model, artifacts_dir / "model.pkl")

        for name, value in metrics.items():
            if isinstance(value, (int, float)):
                _append_metric(metrics_path, name, value)

        logger.info(
            "train.complete",
            extra={"metrics": {k: v for k, v in metrics.items() if isinstance(v, (int, float))}},
        )

        # SHAP ------------------------------------------------------------------
        shap_report: dict[str, Any] = {}
        try:
            sample_n = min(200, len(X_val))
            shap_report = analyze.compute_shap(
                model=model,
                X_sample=X_val.head(sample_n),
                feature_names=feature_names,
                plot_path=artifacts_dir / "shap_global.png",
            )
        except Exception as exc:
            logger.warning("shap.failed", extra={"error": str(exc)})

        # Bias ------------------------------------------------------------------
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
                        plot_path=artifacts_dir / "bias.png",
                    )
                    # Stamp the column names so the backend doesn't have to
                    # reconstruct them from group keys (which may explode on
                    # high-cardinality numeric features the user selected).
                    bias_report["sensitive_features"] = present
                    # Cap groups to keep JSON payload sane when someone
                    # accidentally picks a continuous feature.
                    groups = bias_report.get("groups") or {}
                    if isinstance(groups, dict) and len(groups) > 200:
                        sorted_keys = list(groups.keys())[:200]
                        bias_report["groups"] = {k: groups[k] for k in sorted_keys}
                        bias_report["groups_truncated"] = True
                        bias_report["groups_total"] = len(groups)
                except Exception as exc:
                    logger.warning("bias.failed", extra={"error": str(exc)})
            else:
                logger.info(
                    "bias.skipped",
                    extra={"reason": "sensitive features not in feature frame"},
                )

        # Persist report JSON files for the backend to mirror into Postgres.
        if shap_report:
            (reports_dir / "shap.json").write_text(json.dumps(
                {"global_importance": shap_report.get("global_importance", {})},
                default=str,
            ))
        if bias_report:
            (reports_dir / "bias.json").write_text(json.dumps(bias_report, default=str))

        # Persist a minimal input-schema summary alongside the model for the
        # serving container to load at startup.
        try:
            if hasattr(X_post_sample, "columns"):
                cols = list(X_post_sample.columns)
            else:
                cols = feature_names
            schema_doc = {
                "type": "object",
                "properties": {c: {"type": "number"} for c in cols},
                "title": "ModelInput",
                "flavor": flavor,
                "target": target,
                "target_classes": target_classes,
            }
            (artifacts_dir / "input_schema.json").write_text(json.dumps(schema_doc))
        except Exception as exc:
            logger.warning("input_schema.write_failed", extra={"error": str(exc)})

        duration = time.monotonic() - t_start
        logger.info("trainer.complete", extra={"run_id": run_id, "duration_sec": round(duration, 2)})
        return 0
    except Exception as exc:
        logger.error(
            "trainer.failed",
            extra={"run_id": run_id, "error": str(exc), "trace": traceback.format_exc()},
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
