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


def _append_metric(
    path: Path,
    name: str,
    value: float,
    step: int | None = None,
    phase: str | None = None,
) -> None:
    row: dict[str, Any] = {"name": name, "value": float(value)}
    if step is not None:
        row["step"] = int(step)
    if phase:
        row["phase"] = phase
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")

    # Dual-write to MLflow. No-op when MLFLOW_TRACKING_URI is unset or
    # the tracking server is unreachable — the sink self-disables after
    # the first failure so a down MLflow does not slow down training.
    from platform_trainer import mlflow_sink

    mlflow_sink.log_metric(name, float(value), step=step)


def _feature_names(preprocessor: Any, fallback: list[str]) -> list[str]:
    try:
        raw = [str(n) for n in preprocessor.get_feature_names_out()]
    except Exception:
        return fallback
    return [_clean_feature_name(n) for n in raw]


def _json_safe(value: Any) -> Any:
    """Coerce hyperparameter values into JSON-compatible primitives.

    MLP's ``hidden_layer_sizes`` is a tuple post-coercion; tuples don't
    serialize cleanly across every client so emit them as lists. Anything
    json.dumps already handles (numbers/strings/bools/None) passes through.
    """
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, (list, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return value


def _task_family_for_protocol(fit_protocol: str) -> str:
    """Map fit_protocol → coarse task family the trainer branches on.

    Supervised covers both the default (missing protocol) and the explicit
    sklearn/autogluon protocols. Everything else names its own family.
    """
    if fit_protocol in ("", "sklearn", "autogluon"):
        return "supervised"
    if fit_protocol == "sklearn_cluster":
        return "clustering"
    if fit_protocol == "sktime":
        return "forecasting"
    if fit_protocol in ("surprise", "implicit"):
        return "recommender"
    return "supervised"


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


def _run_clustering(
    *,
    df: pd.DataFrame,
    transform_cfg: dict[str, Any],
    model_catalog: dict[str, Any],
    run_dir: Path,
    artifacts_dir: Path,
    reports_dir: Path,
    metrics_path: Path,
    run_id: str,
    t_start: float,
) -> int:
    """Unsupervised clustering pipeline.

    Shares the preprocessor-once path with supervised runs (ColumnTransformer
    handles scaling/encoding of the user-selected feature columns, no ``y``).
    After fit we wrap the clusterer back into a Pipeline and joblib-dump so
    the serving layer sees the same artifact shape as supervised runs.

    The wizard's "feature columns" selection is honored via the existing
    ``transforms`` list; any column not explicitly kept/dropped falls into
    the ColumnTransformer's auto-passthrough bucket.
    """
    from sklearn.pipeline import Pipeline

    from platform_trainer.adapters import get_adapter

    name = (model_catalog.get("kind") or model_catalog.get("name") or "").strip()
    hyperparams = model_catalog.get("hyperparams") or {}
    signature = model_catalog.get("signature") or {}
    task_class_map = signature.get("task_class_map") or {}
    fit_protocol = (signature.get("fit_protocol") or "sklearn_cluster").strip()

    # Clustering has no target — drop it if the user accidentally sent one
    # (which the wizard shouldn't, but the API accepts arbitrary payloads).
    target = transform_cfg.get("target") or None
    feature_frame = df.drop(columns=[target]) if target and target in df.columns else df

    user_semantic_types = transform_cfg.get("semantic_types") or {}
    schema = transforms.coarse_schema(feature_frame, user_types=user_semantic_types)
    preprocessor, kept_cols = transforms.build_column_transformer(
        transforms=transform_cfg.get("transforms") or [],
        schema=schema,
    )

    # A small validation holdout is useful for an "unbiased" silhouette; if
    # the user didn't configure a split we keep it simple — 80/20.
    split_config = transform_cfg.get("split") or {}
    val_frac = float(split_config.get("val", 0.2) or 0.2)
    val_frac = min(max(val_frac, 0.0), 0.5)
    seed = int(split_config.get("seed", 42))
    from sklearn.model_selection import train_test_split as _tts

    if val_frac > 0 and len(feature_frame) > 10:
        X_train, X_val = _tts(feature_frame, test_size=val_frac, random_state=seed)
    else:
        X_train = feature_frame
        X_val = feature_frame.head(0)

    X_train_np = preprocessor.fit_transform(X_train)
    X_val_np = preprocessor.transform(X_val) if len(X_val) > 0 else None

    adapter = get_adapter(name, fit_protocol=fit_protocol)
    estimator, metrics, effective_hyperparams = adapter.fit_estimator(
        name=name,
        task3="clustering",
        task_class_map=task_class_map,
        X_train=X_train_np,
        y_train=None,
        X_val=X_val_np,
        y_val=None,
        hyperparams=hyperparams,
    )

    # Wrap preprocessor + clusterer into a Pipeline so serving's
    # ``model.predict(DataFrame)`` goes through both stages (inductive case),
    # or through the 1-NN TransductiveClusterer on preprocessed input
    # (transductive case — wrapper still accepts preprocessed arrays).
    model = Pipeline(steps=[("preprocess", preprocessor), ("model", estimator)])
    import joblib

    from platform_trainer.signing import sign_file

    model_path = artifacts_dir / "model.pkl"
    joblib.dump(model, model_path)
    sign_file(model_path)

    # Record metrics so the UI's metrics panel has data to render.
    for metric_name, metric_value in metrics.items():
        if isinstance(metric_value, (int, float)):
            _append_metric(metrics_path, metric_name, float(metric_value))
    logger.info(
        "train.complete",
        extra={
            "metrics": {k: v for k, v in metrics.items() if isinstance(v, (int, float))}
        },
    )

    # Input schema — flavor="clustering" tells the serving layer / predict.py
    # to treat model.predict output as cluster labels, not class probabilities.
    cols = [c for c in kept_cols if c in feature_frame.columns]
    schema_doc = {
        "type": "object",
        "properties": {c: {"type": "number"} for c in cols},
        "title": "ModelInput",
        "flavor": "clustering",
        "serving_mode": (
            "assign"
            if name in {"sklearn_dbscan", "sklearn_agglomerative"}
            else "predict"
        ),
        "target": None,
        "target_classes": None,
        "target_encoded": False,
    }
    (artifacts_dir / "input_schema.json").write_text(json.dumps(schema_doc))

    # selected_hyperparams.json keeps parity with supervised runs.
    try:
        selected_doc = {
            "source": "user",
            "model_name": name,
            "task": "clustering",
            "hyperparameters": {
                str(k): _json_safe(v) for k, v in (effective_hyperparams or {}).items()
            },
        }
        (artifacts_dir / "selected_hyperparams.json").write_text(
            json.dumps(selected_doc, default=str)
        )
    except Exception as exc:
        logger.warning("selected_hyperparams.write_failed", extra={"error": str(exc)})

    duration = time.monotonic() - t_start
    logger.info(
        "trainer.complete",
        extra={
            "run_id": run_id,
            "duration_sec": round(duration, 2),
            "family": "clustering",
        },
    )
    # Reports dir stays empty for clustering — SHAP/bias are supervised-only.
    _ = reports_dir  # keep signature stable; reports dir is pre-created.
    return 0


def _run_forecasting(
    *,
    df: pd.DataFrame,
    transform_cfg: dict[str, Any],
    model_catalog: dict[str, Any],
    run_dir: Path,
    artifacts_dir: Path,
    reports_dir: Path,
    metrics_path: Path,
    run_id: str,
    t_start: float,
) -> int:
    """Univariate forecasting pipeline.

    Expects ``transform_cfg['roles']`` to carry ``time_column``,
    ``target_column`` (the value to forecast), and ``horizon``. The training
    split is a temporal holdout: the last ``val_frac`` of rows go to
    validation, the rest to training. Random splits are forbidden here —
    they leak future-into-past.
    """
    from platform_trainer.adapters import get_adapter

    name = (model_catalog.get("kind") or model_catalog.get("name") or "").strip()
    hyperparams = model_catalog.get("hyperparams") or {}
    signature = model_catalog.get("signature") or {}
    fit_protocol = (signature.get("fit_protocol") or "sktime").strip()

    roles = transform_cfg.get("roles") or {}
    time_col = roles.get("time_column") or transform_cfg.get("time_column")
    value_col = roles.get("target_column") or transform_cfg.get("target")
    horizon = int(roles.get("horizon") or 12)
    if not time_col or not value_col:
        raise ValueError(
            "forecasting requires transform_cfg.roles.time_column and target_column"
        )
    if time_col not in df.columns:
        raise ValueError(f"time column {time_col!r} not in dataset")
    if value_col not in df.columns:
        raise ValueError(f"value column {value_col!r} not in dataset")

    # Build the y Series indexed by parsed time, sorted ascending. pandas'
    # ``to_datetime`` handles most ISO / locale formats; non-parseable entries
    # become NaT and get dropped.
    ts = pd.to_datetime(df[time_col], errors="coerce")
    y = pd.Series(df[value_col].values, index=pd.DatetimeIndex(ts))
    y = y[~y.index.isna()].dropna()

    # Real datasets commonly have duplicate timestamps (multi-SKU rows on the
    # same day, multi-store per hour, …). sktime/statsmodels wrap the series
    # in a stats ``DatetimeIndex`` and require both uniqueness AND a known
    # frequency — otherwise `.predict(fh=…)` blows up in
    # `DatetimeIndex.to_period(freq)` with "You must pass a freq argument as
    # current index has none."  Collapse dups by sum (additive for sales /
    # counts, which is the default forecasting use case).
    dup_count = int(y.index.duplicated().sum())
    if dup_count:
        y = y.groupby(level=0).sum()
        logger.info(
            "forecasting.dedup",
            extra={"duplicates_collapsed": dup_count, "rows_after": len(y)},
        )
    y = y.sort_index()

    # Try to infer a frequency from the (now-unique) timestamps. If that fails
    # — irregular dates, gaps, mixed cadence — fall back to daily resampling
    # with ``sum`` (which fills gap days with 0, a reasonable prior for sales).
    inferred_freq = None
    try:
        inferred_freq = pd.infer_freq(y.index)
    except Exception:  # noqa: BLE001
        inferred_freq = None
    if inferred_freq:
        y.index.freq = inferred_freq  # type: ignore[misc]
    else:
        logger.info("forecasting.resample_daily", extra={"reason": "freq_not_inferred"})
        y = y.resample("D").sum()
        y.index.freq = "D"  # type: ignore[misc]
        inferred_freq = "D"

    if len(y) < max(horizon + 5, 20):
        raise ValueError(
            f"series too short for forecasting after dedup/resample: "
            f"{len(y)} rows, need >= {max(horizon + 5, 20)}"
        )

    # Temporal split: last `horizon` rows go to validation so the metric
    # reflects an out-of-sample forecast of the requested length.
    y_train = y.iloc[:-horizon]
    y_val = y.iloc[-horizon:]

    adapter = get_adapter(name, fit_protocol=fit_protocol)
    forecaster, metrics, effective_hyperparams = adapter.fit_estimator(
        name=name,
        task3="forecasting",
        task_class_map=(signature.get("task_class_map") or {}),
        X_train=None,
        y_train=y_train,
        X_val=None,
        y_val=y_val,
        hyperparams=hyperparams,
    )

    # Persist the fitted forecaster. sktime forecasters pickle cleanly; the
    # serving layer loads it with joblib the same way as sklearn models.
    import joblib

    from platform_trainer.signing import sign_file

    model_path = artifacts_dir / "model.pkl"
    joblib.dump(forecaster, model_path)
    sign_file(model_path)

    for metric_name, metric_value in metrics.items():
        if isinstance(metric_value, (int, float)):
            _append_metric(metrics_path, metric_name, float(metric_value))
    logger.info(
        "train.complete",
        extra={
            "metrics": {
                k: v for k, v in metrics.items() if isinstance(v, (int, float))
            },
            "family": "forecasting",
        },
    )

    # Save the training series so the serving container can reconstruct the
    # ForecastingHorizon against the same end date. predict.py reads this.
    try:
        y.to_frame("value").to_csv(artifacts_dir / "y_train.csv", index_label="ts")
    except Exception as exc:
        logger.warning("forecasting.y_train_write_failed", extra={"error": str(exc)})

    schema_doc = {
        "type": "object",
        "properties": {"horizon": {"type": "integer"}},
        "title": "ForecastInput",
        "flavor": "forecasting",
        "serving_mode": "forecast",
        "target": value_col,
        "time_column": time_col,
        "horizon": horizon,
        "last_train_timestamp": str(y.index[-1]) if len(y) else None,
        "frequency": inferred_freq,
        "target_classes": None,
        "target_encoded": False,
    }
    (artifacts_dir / "input_schema.json").write_text(json.dumps(schema_doc))

    try:
        selected_doc = {
            "source": "user",
            "model_name": name,
            "task": "forecasting",
            "hyperparameters": {
                str(k): _json_safe(v) for k, v in (effective_hyperparams or {}).items()
            },
        }
        (artifacts_dir / "selected_hyperparams.json").write_text(
            json.dumps(selected_doc, default=str)
        )
    except Exception as exc:
        logger.warning("selected_hyperparams.write_failed", extra={"error": str(exc)})

    duration = time.monotonic() - t_start
    logger.info(
        "trainer.complete",
        extra={
            "run_id": run_id,
            "duration_sec": round(duration, 2),
            "family": "forecasting",
        },
    )
    _ = reports_dir
    _ = run_dir
    return 0


def _run_recommender(
    *,
    df: pd.DataFrame,
    transform_cfg: dict[str, Any],
    model_catalog: dict[str, Any],
    run_dir: Path,
    artifacts_dir: Path,
    reports_dir: Path,
    metrics_path: Path,
    run_id: str,
    t_start: float,
) -> int:
    """Collaborative-filtering pipeline (Surprise or implicit)."""
    from platform_trainer.adapters import get_adapter

    name = (model_catalog.get("kind") or model_catalog.get("name") or "").strip()
    hyperparams = model_catalog.get("hyperparams") or {}
    signature = model_catalog.get("signature") or {}
    fit_protocol = (signature.get("fit_protocol") or "surprise").strip()

    roles = transform_cfg.get("roles") or {}
    user_col = roles.get("user_column")
    item_col = roles.get("item_column")
    rating_col = roles.get("rating_column")
    feedback_type = roles.get("feedback_type") or "explicit"
    if not user_col or not item_col or not rating_col:
        raise ValueError(
            "recommender requires transform_cfg.roles "
            "user_column / item_column / rating_column"
        )
    for c in (user_col, item_col, rating_col):
        if c not in df.columns:
            raise ValueError(f"column {c!r} not in dataset")

    interactions = df[[user_col, item_col, rating_col]].dropna()
    interactions.columns = ["user_id", "item_id", "rating"]

    adapter = get_adapter(name, fit_protocol=fit_protocol)
    model, metrics, effective_hyperparams = adapter.fit_estimator(
        name=name,
        task3="recommender",
        task_class_map=(signature.get("task_class_map") or {}),
        X_train=None,
        y_train=None,
        X_val=None,
        y_val=None,
        hyperparams={
            **hyperparams,
            "_interactions": interactions,
            "_feedback_type": feedback_type,
            "_split_seed": int((transform_cfg.get("split") or {}).get("seed", 42)),
        },
    )

    import joblib

    from platform_trainer.signing import sign_file

    model_path = artifacts_dir / "model.pkl"
    joblib.dump(model, model_path)
    sign_file(model_path)

    for metric_name, metric_value in metrics.items():
        if isinstance(metric_value, (int, float)):
            _append_metric(metrics_path, metric_name, float(metric_value))
    logger.info(
        "train.complete",
        extra={
            "metrics": {
                k: v for k, v in metrics.items() if isinstance(v, (int, float))
            },
            "family": "recommender",
        },
    )

    schema_doc = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "item_id": {"type": "string"},
            "k": {"type": "integer"},
        },
        "title": "RecommenderInput",
        "flavor": "recommender",
        "serving_mode": (
            "recommend_topk" if feedback_type == "implicit" else "recommend_score"
        ),
        "user_column": user_col,
        "item_column": item_col,
        "rating_column": rating_col,
        "feedback_type": feedback_type,
        "target": None,
        "target_classes": None,
        "target_encoded": False,
    }
    (artifacts_dir / "input_schema.json").write_text(json.dumps(schema_doc))

    try:
        selected_doc = {
            "source": "user",
            "model_name": name,
            "task": "recommender",
            "hyperparameters": {
                str(k): _json_safe(v)
                for k, v in (effective_hyperparams or {}).items()
                if not str(k).startswith("_")
            },
        }
        (artifacts_dir / "selected_hyperparams.json").write_text(
            json.dumps(selected_doc, default=str)
        )
    except Exception as exc:
        logger.warning("selected_hyperparams.write_failed", extra={"error": str(exc)})

    duration = time.monotonic() - t_start
    logger.info(
        "trainer.complete",
        extra={
            "run_id": run_id,
            "duration_sec": round(duration, 2),
            "family": "recommender",
        },
    )
    _ = reports_dir
    _ = run_dir
    return 0


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

    logger.info(
        "trainer.start", extra={"run_id": run_id, "dataset_path": str(dataset_path)}
    )

    # Begin the MLflow run at the very top of training so every subsequent
    # _append_metric / log_param / log_artifact attaches to it. Experiment
    # name comes from the env the worker injects (falls back to 'default').
    # If MLflow is unreachable the sink self-disables; training proceeds
    # exactly as before.
    from platform_trainer import mlflow_sink

    mlflow_experiment_name = _env("MLFLOW_EXPERIMENT_NAME") or "default"
    mlflow_sink.begin(
        run_id=run_id,
        experiment_name=mlflow_experiment_name,
        tags={
            "platform.dataset_path": str(dataset_path),
            "platform.run_dir": str(run_dir),
        },
    )

    try:
        transform_cfg = json.loads(_env("TRANSFORM_CONFIG") or "{}")
        model_catalog = json.loads(_env("MODEL_CATALOG") or "{}")
        sensitive_features = json.loads(_env("SENSITIVE_FEATURES") or "[]")
        if not isinstance(sensitive_features, list):
            raise ValueError("SENSITIVE_FEATURES must be a JSON list")

        # Peek at MODEL_CATALOG to decide whether this is a supervised run
        # (needs a target column) or an unsupervised family like clustering
        # (no target, just feature columns). The signature drives the branch.
        model_catalog_peek = json.loads(_env("MODEL_CATALOG") or "{}")
        signature_peek = model_catalog_peek.get("signature") or {}
        fit_protocol_peek = (signature_peek.get("fit_protocol") or "").strip().lower()
        task_family_peek = _task_family_for_protocol(fit_protocol_peek)

        target = transform_cfg.get("target")
        if task_family_peek == "supervised" and not target:
            raise ValueError("TRANSFORM_CONFIG.target is required for supervised runs")

        df = _read_dataset(dataset_path)
        if target and target not in df.columns:
            # Clustering may legitimately have no target; only check membership
            # when one was supplied.
            raise ValueError(f"target column {target!r} not in dataset")

        if task_family_peek == "clustering":
            return _run_clustering(
                df=df,
                transform_cfg=transform_cfg,
                model_catalog=model_catalog_peek,
                run_dir=run_dir,
                artifacts_dir=artifacts_dir,
                reports_dir=reports_dir,
                metrics_path=metrics_path,
                run_id=run_id,
                t_start=t_start,
            )
        if task_family_peek == "forecasting":
            return _run_forecasting(
                df=df,
                transform_cfg=transform_cfg,
                model_catalog=model_catalog_peek,
                run_dir=run_dir,
                artifacts_dir=artifacts_dir,
                reports_dir=reports_dir,
                metrics_path=metrics_path,
                run_id=run_id,
                t_start=t_start,
            )
        if task_family_peek == "recommender":
            return _run_recommender(
                df=df,
                transform_cfg=transform_cfg,
                model_catalog=model_catalog_peek,
                run_dir=run_dir,
                artifacts_dir=artifacts_dir,
                reports_dir=reports_dir,
                metrics_path=metrics_path,
                run_id=run_id,
                t_start=t_start,
            )

        # The API may have persisted a user-chosen task override inside
        # MODEL_CATALOG (see apps/api/.../runs router). If absent or invalid,
        # fall back to the three-way heuristic on the target column. All
        # downstream logic works off the three-way label; ``coarse_task`` maps
        # it back to the two-way enum where needed.
        model_catalog_for_task = json.loads(_env("MODEL_CATALOG") or "{}")
        requested_task = (model_catalog_for_task.get("task") or "").strip()
        valid_tasks3 = {
            "regression",
            "binary_classification",
            "multiclass_classification",
        }
        if requested_task in valid_tasks3:
            task3 = requested_task  # type: ignore[assignment]
        else:
            task3 = transforms.infer_task_3way(df[target])
        task = transforms.coarse_task(task3)
        logger.info(
            "task.inferred",
            extra={
                "task": task,
                "task3": task3,
                "rows": len(df),
                "source": ("user" if requested_task in valid_tasks3 else "inferred"),
            },
        )

        # Auto label-encode non-numeric classification targets so every adapter
        # (XGBoost/LightGBM/AutoGluon/sklearn) sees numeric y. Capture the
        # class labels either way so serving can map integer predictions
        # back to a human-readable string.
        target_classes: list[str] | None = None
        target_encoded: bool = False
        if task == "classification":
            y_series = df[target]
            if not pd.api.types.is_numeric_dtype(
                y_series
            ) or pd.api.types.is_bool_dtype(y_series):
                from sklearn.preprocessing import LabelEncoder

                target_label_encoder = LabelEncoder().fit(y_series)
                df[target] = target_label_encoder.transform(y_series)
                target_classes = [str(c) for c in target_label_encoder.classes_]
                target_encoded = True
                logger.info(
                    "target.label_encoded",
                    extra={"classes": target_classes, "n": len(target_classes)},
                )
            else:
                # Numeric target — still record the unique values so the UI
                # can show "0 = 0, 1 = 1, …" context alongside the prediction.
                uniques = sorted(y_series.dropna().unique().tolist())
                target_classes = [str(v) for v in uniques]

        X_train, X_val, X_test, y_train, y_val, y_test = transforms.apply_split(
            df,
            target=target,
            split_config=transform_cfg.get("split") or {},
            task=task,
        )

        user_semantic_types = transform_cfg.get("semantic_types") or {}
        schema = transforms.coarse_schema(
            df.drop(columns=[target]), user_types=user_semantic_types
        )
        preprocessor, kept_cols = transforms.build_column_transformer(
            transforms=transform_cfg.get("transforms") or [],
            schema=schema,
        )

        name = (model_catalog.get("kind") or model_catalog.get("name") or "").strip()
        hyperparams = model_catalog.get("hyperparams") or {}
        signature = model_catalog.get("signature") or {}
        task_class_map = signature.get("task_class_map") or {}
        fit_protocol = (signature.get("fit_protocol") or "").strip() or None
        hpo_cfg = model_catalog.get("hpo") or None
        hpo_enabled = bool(hpo_cfg and hpo_cfg.get("enabled"))
        # AutoGluon carries ``time_limit`` / ``presets`` as regular hyperparams
        # on the new catalog shape; accept both the flat legacy payload and
        # the nested hyperparams dict to keep old runs working.
        time_limit = (
            int(model_catalog.get("time_limit") or hyperparams.get("time_limit") or 0)
            or None
        )
        presets = (
            model_catalog.get("presets")
            or hyperparams.get("presets")
            or "medium_quality"
        )

        adapter = get_adapter(name, fit_protocol=fit_protocol)

        model: Any
        metrics: dict[str, Any]
        feature_names: list[str]
        flavor: str
        effective_hyperparams: dict[str, Any] = {}
        hpo_report: dict[str, Any] | None = None

        if name == "autogluon":
            # AutoGluon has no sklearn preprocessor in front of it, so we honor
            # the user's column selection by hand: kept_cols comes from
            # build_column_transformer, which already accounts for explicit
            # drops (op=="drop") and implicit drops (text columns).
            feature_cols = [c for c in kept_cols if c in X_train.columns]
            if not feature_cols:
                raise ValueError("no feature columns selected for training")
            X_train = X_train[feature_cols]
            X_val = X_val[feature_cols]
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
            effective_hyperparams = {
                "time_limit": time_limit,
                "presets": presets,
                **(hyperparams or {}),
            }
            flavor = "autogluon"
            feature_names = feature_cols
            X_post_sample = X_val
            y_pred = model.predict(X_val)
        else:
            # Fit the preprocessor once so HPO trials (and any future multi-fit
            # path) don't pay a re-fit cost per candidate. Adapters receive
            # already-transformed numpy arrays; we re-wrap into a Pipeline here
            # so SHAP, bias, and serving see the same artifact shape as before.
            X_train_np = preprocessor.fit_transform(X_train, y_train)
            X_val_np = preprocessor.transform(X_val)

            from sklearn.pipeline import Pipeline

            if hpo_enabled:
                from platform_trainer import hpo as hpo_mod

                seed = int((transform_cfg.get("split") or {}).get("seed", 42))
                search_space = hpo_cfg.get("search_space") or {}
                n_trials = int(hpo_cfg.get("n_trials") or 30)
                timeout_sec = int(hpo_cfg.get("timeout_sec") or 1800)
                metric_override = hpo_cfg.get("metric") or None
                direction_override = hpo_cfg.get("direction") or None

                if name.startswith("sklearn_"):

                    def _prep(hp: dict[str, Any]) -> dict[str, Any]:
                        return adapter.prepare_hyperparams(name, hp)

                    estimator, metrics, hpo_report, label_encoder = hpo_mod.run_hpo(
                        name=name,
                        task3=task3,
                        task_class_map=task_class_map,
                        X_train=X_train_np,
                        y_train=y_train,
                        X_val=X_val_np,
                        y_val=y_val,
                        fixed_hyperparams={},
                        search_space=search_space,
                        n_trials=n_trials,
                        timeout_sec=timeout_sec,
                        metric=metric_override,
                        direction=direction_override,
                        seed=seed,
                        prepare_hyperparams=_prep,
                    )
                else:

                    def _prep_bt(hp: dict[str, Any]) -> dict[str, Any]:
                        return adapter.prepare_hyperparams(name, task3, hp)

                    estimator, metrics, hpo_report, label_encoder = hpo_mod.run_hpo(
                        name=name,
                        task3=task3,
                        task_class_map=task_class_map,
                        X_train=X_train_np,
                        y_train=y_train,
                        X_val=X_val_np,
                        y_val=y_val,
                        fixed_hyperparams={},
                        search_space=search_space,
                        n_trials=n_trials,
                        timeout_sec=timeout_sec,
                        metric=metric_override,
                        direction=direction_override,
                        seed=seed,
                        prepare_hyperparams=_prep_bt,
                        encode_labels=adapter.encode_labels,
                    )
                effective_hyperparams = hpo_report.get("best_params", {})
                logger.info(
                    "hpo.complete",
                    extra={
                        "metric": hpo_report.get("metric"),
                        "best_value": hpo_report.get("best_value"),
                        "trials": hpo_report.get("n_trials_completed"),
                    },
                )
            elif name.startswith("sklearn_"):
                estimator, metrics, effective_hyperparams = adapter.fit_estimator(
                    name=name,
                    task3=task3,
                    task_class_map=task_class_map,
                    X_train=X_train_np,
                    y_train=y_train,
                    X_val=X_val_np,
                    y_val=y_val,
                    hyperparams=hyperparams,
                )
                label_encoder = None
            else:
                (
                    estimator,
                    metrics,
                    effective_hyperparams,
                    label_encoder,
                ) = adapter.fit_estimator(
                    name=name,
                    task3=task3,
                    task_class_map=task_class_map,
                    X_train=X_train_np,
                    y_train=y_train,
                    X_val=X_val_np,
                    y_val=y_val,
                    hyperparams=hyperparams,
                )

            model = Pipeline(steps=[("preprocess", preprocessor), ("model", estimator)])
            if label_encoder is not None:
                # Attribute carries through joblib.dump so serving can decode
                # integer class predictions back to original labels.
                model.label_encoder_ = label_encoder  # type: ignore[attr-defined]
            flavor = "sklearn"
            feature_names = _feature_names(preprocessor, kept_cols)
            X_post_sample = X_val_np
            y_pred = estimator.predict(X_val_np)

            # Persist the fitted pipeline (preprocessor + estimator) for serving.
            import joblib

            from platform_trainer.signing import sign_file

            _mpath = artifacts_dir / "model.pkl"
            joblib.dump(model, _mpath)
            sign_file(_mpath)

        # Held-out test-set scoring. apply_split reserves a third fold
        # (default 15%) that's never touched during HPO or final fit, so
        # test_* metrics are an unbiased report card. Validation metrics
        # are optimistic because HPO repeatedly scored against them.
        _test_metrics: dict[str, float] = {}
        try:
            if name == "autogluon":
                from platform_trainer.adapters import autogluon as _ag_mod

                _test_df = X_test[feature_cols].copy()
                _test_df[target] = y_test.values
                _test_metrics = _ag_mod.score_predictor(
                    predictor=model, df=_test_df, target=target, task=task
                )
            else:
                _X_test_np = preprocessor.transform(X_test)
                if name.startswith("sklearn_"):
                    _test_metrics = adapter.score_estimator(
                        task3=task3,
                        estimator=estimator,
                        X=_X_test_np,
                        y=y_test,
                    )
                else:
                    _test_metrics = adapter.score_estimator(
                        task3=task3,
                        estimator=estimator,
                        X=_X_test_np,
                        y=y_test,
                        label_encoder=label_encoder,
                    )
        except Exception as _exc:  # noqa: BLE001 — test scoring is best-effort
            logger.warning("test_metrics.failed", extra={"error": str(_exc)})
        for _k, _v in _test_metrics.items():
            if isinstance(_v, (int, float)):
                metrics[f"test_{_k}"] = float(_v)

        for _metric_name, _metric_value in metrics.items():
            if isinstance(_metric_value, (int, float)):
                _append_metric(metrics_path, _metric_name, _metric_value)

        logger.info(
            "train.complete",
            extra={
                "metrics": {
                    k: v for k, v in metrics.items() if isinstance(v, (int, float))
                }
            },
        )

        # Feature importance ----------------------------------------------------
        # SHAP's KernelExplainer doesn't play with AutoGluon's TabularPredictor
        # (predict_proba wants a DataFrame, SHAP hands it numpy), so for the
        # AutoGluon path we use its native feature_importance(val_df) which
        # runs permutation importance on the ensemble. Everything else goes
        # through the regular SHAP pipeline.
        shap_report: dict[str, Any] = {}
        if name == "autogluon":
            try:
                val_df_with_target = X_val.copy()
                val_df_with_target[target] = y_val.values
                fi = model.feature_importance(val_df_with_target)
                importance: dict[str, float] = {}
                for feat, row in fi.iterrows():
                    val = (
                        row.get("importance")
                        if hasattr(row, "get")
                        else row["importance"]
                    )
                    if val is None or pd.isna(val):
                        continue
                    importance[str(feat)] = float(val)
                shap_report = {"global_importance": importance}

                # Matplotlib horizontal bar, same shape as the sklearn path.
                try:
                    from platform_trainer.analyze import _save_importance_plot

                    _save_importance_plot(importance, artifacts_dir / "shap_global.png")
                except Exception as exc:
                    logger.info("autogluon.plot_failed", extra={"error": str(exc)})
            except Exception as exc:
                logger.warning(
                    "autogluon.feature_importance_failed", extra={"error": str(exc)}
                )
        else:
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
            (reports_dir / "shap.json").write_text(
                json.dumps(
                    {"global_importance": shap_report.get("global_importance", {})},
                    default=str,
                )
            )
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
                "target_encoded": target_encoded,
            }
            (artifacts_dir / "input_schema.json").write_text(json.dumps(schema_doc))
        except Exception as exc:
            logger.warning("input_schema.write_failed", extra={"error": str(exc)})

        # selected_hyperparams.json — the exact set the estimator was
        # instantiated with. Source is ``hpo`` when Optuna picked the values,
        # ``user`` otherwise.
        try:
            source = "hpo" if hpo_enabled and hpo_report is not None else "user"
            selected_doc: dict[str, Any] = {
                "source": source,
                "model_name": name,
                "task": task3,
                "hyperparameters": {
                    str(k): _json_safe(v)
                    for k, v in (effective_hyperparams or {}).items()
                },
            }
            if source == "hpo" and hpo_report is not None:
                selected_doc["hpo_summary"] = {
                    "n_trials_completed": hpo_report.get("n_trials_completed"),
                    "best_value": hpo_report.get("best_value"),
                    "metric": hpo_report.get("metric"),
                    "direction": hpo_report.get("direction"),
                    "search_space": _json_safe(hpo_report.get("search_space") or {}),
                }
            (artifacts_dir / "selected_hyperparams.json").write_text(
                json.dumps(selected_doc, default=str)
            )
        except Exception as exc:
            logger.warning(
                "selected_hyperparams.write_failed", extra={"error": str(exc)}
            )

        # reports/hpo.json — full Optuna study summary (per-trial list capped
        # at 200). Only written on the HPO path.
        if hpo_enabled and hpo_report is not None:
            try:
                (reports_dir / "hpo.json").write_text(
                    json.dumps(_json_safe(hpo_report), default=str)
                )
            except Exception as exc:
                logger.warning("hpo_report.write_failed", extra={"error": str(exc)})

        duration = time.monotonic() - t_start
        logger.info(
            "trainer.complete",
            extra={"run_id": run_id, "duration_sec": round(duration, 2)},
        )

        # Dual-write the artifact tree + selected_hyperparams + reports to
        # MLflow so the tracking UI has the full run context. Local
        # JSONL / disk paths remain authoritative until Batch 35.
        try:
            mlflow_sink.log_artifact(artifacts_dir, artifact_path="artifacts")
            mlflow_sink.log_artifact(reports_dir, artifact_path="reports")
            mlflow_sink.log_artifact(metrics_path, artifact_path=None)
        except Exception as exc:  # noqa: BLE001 — telemetry must not fail the run
            logger.warning("mlflow.artifact_sync_failed", extra={"error": str(exc)})
        mlflow_sink.end("FINISHED")

        return 0
    except Exception as exc:
        logger.error(
            "trainer.failed",
            extra={
                "run_id": run_id,
                "error": str(exc),
                "trace": traceback.format_exc(),
            },
        )
        mlflow_sink.end("FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
