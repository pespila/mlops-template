"""Optuna-based hyperparameter search for sklearn / XGBoost / LightGBM.

Operates on pre-transformed numpy arrays — ``__main__.py`` fits the
ColumnTransformer once before calling :func:`run_hpo` so trials don't pay a
re-fit cost per candidate. AutoGluon is not routed here; it has its own
internal HPO invoked via ``hyperparameter_tune_kwargs``.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

import numpy as np
import optuna
import pandas as pd
from optuna.samplers import TPESampler
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)


logger = logging.getLogger("platform_trainer.hpo")


_METRIC_DEFAULTS = {
    "regression": ("r2", "maximize"),
    "binary_classification": ("auroc", "maximize"),
    "multiclass_classification": ("accuracy", "maximize"),
}


def _default_metric_and_direction(task3: str) -> tuple[str, str]:
    return _METRIC_DEFAULTS.get(task3, ("accuracy", "maximize"))


def _resolve_class(dotted_path: str) -> Any:
    mod_path, _, cls_name = dotted_path.rpartition(".")
    if not mod_path:
        raise ValueError(f"invalid dotted class path: {dotted_path!r}")
    mod = importlib.import_module(mod_path)
    return getattr(mod, cls_name)


def _suggest(trial: optuna.Trial, name: str, spec: dict[str, Any]) -> Any:
    stype = spec.get("type")
    if stype == "int":
        low = int(spec["low"])
        high = int(spec["high"])
        step = spec.get("step") or 1
        return trial.suggest_int(name, low, high, step=step, log=bool(spec.get("log")))
    if stype == "float":
        return trial.suggest_float(
            name,
            float(spec["low"]),
            float(spec["high"]),
            log=bool(spec.get("log")),
        )
    if stype == "categorical":
        choices = list(spec.get("choices") or [])
        if not choices:
            raise ValueError(f"categorical {name!r} has no choices")
        return trial.suggest_categorical(name, choices)
    raise ValueError(f"unknown search-space type for {name!r}: {stype!r}")


def _full_metrics(
    estimator: Any, X_val: np.ndarray, y_val: pd.Series, task3: str
) -> dict[str, float]:
    """Return the same metric bundle adapters produce for single-fit runs.

    Classification -> accuracy + f1_macro + auroc + log_loss (when proba is
    available). Regression -> mae + rmse + r2.
    """
    if task3 == "regression":
        y_pred = estimator.predict(X_val)
        return {
            "mae": float(mean_absolute_error(y_val, y_pred)),
            "rmse": float(np.sqrt(mean_squared_error(y_val, y_pred))),
            "r2": float(r2_score(y_val, y_pred)),
        }
    y_pred = estimator.predict(X_val)
    out: dict[str, float] = {
        "accuracy": float(accuracy_score(y_val, y_pred)),
        "f1_macro": float(f1_score(y_val, y_pred, average="macro", zero_division=0)),
    }
    if hasattr(estimator, "predict_proba"):
        try:
            proba = estimator.predict_proba(X_val)
            if proba.shape[1] == 2:
                out["auroc"] = float(roc_auc_score(y_val, proba[:, 1]))
            else:
                out["auroc"] = float(
                    roc_auc_score(y_val, proba, multi_class="ovr", average="macro")
                )
            out["log_loss"] = float(log_loss(y_val, proba))
        except (ValueError, AttributeError):
            pass
    return out


def _score(
    estimator: Any,
    X_val: np.ndarray,
    y_val: pd.Series,
    task3: str,
    metric: str,
) -> float:
    y_pred = estimator.predict(X_val)
    if metric == "r2":
        return float(r2_score(y_val, y_pred))
    if metric == "mae":
        # We maximize by default; MAE is a loss, so negate when used as a
        # maximize objective — the caller's direction lever handles this.
        return float(mean_absolute_error(y_val, y_pred))
    if metric == "accuracy":
        return float(accuracy_score(y_val, y_pred))
    if metric == "f1_macro":
        return float(f1_score(y_val, y_pred, average="macro", zero_division=0))
    if metric == "auroc":
        if not hasattr(estimator, "predict_proba"):
            # fall back to accuracy when the estimator can't emit probabilities
            return float(accuracy_score(y_val, y_pred))
        proba = estimator.predict_proba(X_val)
        if task3 == "binary_classification" and proba.shape[1] == 2:
            return float(roc_auc_score(y_val, proba[:, 1]))
        return float(
            roc_auc_score(y_val, proba, multi_class="ovr", average="macro")
        )
    raise ValueError(f"unsupported HPO metric: {metric!r}")


def run_hpo(
    *,
    name: str,
    task3: str,
    task_class_map: dict[str, str],
    X_train: np.ndarray,
    y_train: pd.Series,
    X_val: np.ndarray,
    y_val: pd.Series,
    fixed_hyperparams: dict[str, Any],
    search_space: dict[str, dict[str, Any]],
    n_trials: int = 30,
    timeout_sec: int = 1800,
    metric: str | None = None,
    direction: str | None = None,
    seed: int = 42,
    prepare_hyperparams: Any = None,
    encode_labels: Any = None,
) -> tuple[Any, dict[str, float], dict[str, Any], Any | None]:
    """Run an Optuna study and return the best bare estimator.

    Returns ``(best_estimator, best_metrics, hpo_report, label_encoder)``.

    ``prepare_hyperparams`` (optional) is the adapter's ``_prepare_hyperparams``
    function — wraps the trial dict with per-family defaults + type coercion.
    ``encode_labels`` (optional) is the boosted-trees adapter helper that
    returns a label encoder so XGBoost / LightGBM see integer classes.

    The preprocessor is already fit + applied by the caller; ``X_train`` /
    ``X_val`` are numpy. The returned estimator is bare (no preprocessor).
    """
    if not search_space:
        raise ValueError("HPO enabled but search_space is empty")

    metric = metric or _default_metric_and_direction(task3)[0]
    direction = direction or _default_metric_and_direction(task3)[1]

    dotted = task_class_map.get(task3)
    if not dotted:
        supported = list(task_class_map.keys())
        raise ValueError(
            f"model {name!r} does not support task {task3!r} (supports: {supported})"
        )
    cls = _resolve_class(dotted)

    # Classification labels for XGB / LGBM need integer encoding once.
    y_train_fit: pd.Series = y_train
    y_val_fit: pd.Series = y_val
    label_encoder: Any = None
    if encode_labels is not None:
        y_train_fit, y_val_fit, label_encoder = encode_labels(task3, y_train, y_val)

    logger.info(
        "hpo.start",
        extra={
            "model_name": name,
            "task3": task3,
            "metric": metric,
            "direction": direction,
            "n_trials": n_trials,
            "timeout_sec": timeout_sec,
            "search_space_keys": sorted(search_space.keys()),
        },
    )

    per_trial: list[dict[str, Any]] = []

    def objective(trial: optuna.Trial) -> float:
        sampled = {n: _suggest(trial, n, s) for n, s in search_space.items()}
        merged = dict(fixed_hyperparams or {})
        merged.update(sampled)
        effective = prepare_hyperparams(merged) if prepare_hyperparams else merged
        estimator = cls(**effective)
        estimator.fit(X_train, y_train_fit)
        value = _score(estimator, X_val, y_val_fit, task3, metric)
        per_trial.append(
            {"params": {str(k): v for k, v in sampled.items()}, "value": float(value)}
        )
        # Stash the fitted estimator + effective hyperparams on the trial so
        # we can pull the best one out at the end without re-fitting.
        trial.set_user_attr("estimator", estimator)
        trial.set_user_attr("effective", effective)
        return value

    sampler = TPESampler(seed=seed)
    study = optuna.create_study(direction=direction, sampler=sampler)
    try:
        study.optimize(objective, n_trials=n_trials, timeout=timeout_sec, gc_after_trial=True)
    except KeyboardInterrupt:  # pragma: no cover — trainer is non-interactive
        pass

    completed = [t for t in study.trials if t.state.name == "COMPLETE"]
    if not completed:
        raise RuntimeError("HPO produced zero completed trials")

    best_trial = study.best_trial
    best_estimator = best_trial.user_attrs.get("estimator")
    best_effective = best_trial.user_attrs.get("effective") or best_trial.params

    # Re-score the best estimator over the full metric set so the run's
    # metrics panel doesn't show only the single optimized metric.
    best_metrics = _full_metrics(best_estimator, X_val, y_val_fit, task3)
    best_metrics[metric] = float(best_trial.value)
    report = {
        "n_trials_completed": len(completed),
        "best_value": float(best_trial.value),
        "metric": metric,
        "direction": direction,
        "search_space": search_space,
        "best_params": {str(k): v for k, v in best_trial.params.items()},
        # Cap the trial list so we don't blow up the JSON for large studies.
        "per_trial": per_trial[:200],
    }

    logger.info(
        "hpo.done",
        extra={
            "best_value": report["best_value"],
            "n_trials_completed": report["n_trials_completed"],
        },
    )

    return best_estimator, best_metrics, report, label_encoder


def write_report(path: Any, report: dict[str, Any], best_effective: dict[str, Any]) -> None:
    """Write ``reports/hpo.json`` alongside the Optuna summary.

    ``best_effective`` is the full kwargs dict actually passed to the
    estimator (library defaults + best trial params + any family injections)
    so the Model tab can render it as the HPO "selected hyperparameters".
    """
    import json

    payload = {**report, "best_effective": best_effective}
    with open(path, "w") as f:
        json.dump(payload, f, default=str)


__all__ = ["run_hpo", "write_report"]
