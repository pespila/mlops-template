"""Adapter for sklearn-compatible estimators.

Resolves the estimator class at runtime from the catalog entry's
``task_class_map`` (keyed by the three-way task label) so the adapter does not
hard-code per-model imports. Operates on already-preprocessed numpy arrays:
``__main__.py`` fits the ColumnTransformer once before calling this adapter so
HPO trials don't pay a re-fit cost per candidate.
"""

from __future__ import annotations

import ast
import importlib
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)

# Per-family injected defaults — keep the catalog schema free of sklearn-isms
# like `max_iter=1000` that users rarely tune but the estimators need for
# convergence. These layer underneath the user-supplied hyperparams.
_DEFAULT_HYPERPARAMS: dict[str, dict[str, Any]] = {
    "sklearn_logistic": {"max_iter": 1000},
    "sklearn_mlp": {"max_iter": 200},
    "sklearn_svm": {},
}


def _resolve_class(dotted_path: str) -> Any:
    mod_path, _, cls_name = dotted_path.rpartition(".")
    if not mod_path:
        raise ValueError(f"invalid dotted class path: {dotted_path!r}")
    mod = importlib.import_module(mod_path)
    return getattr(mod, cls_name)


def _coerce_tuple(value: Any) -> Any:
    """MLP's ``hidden_layer_sizes`` is transmitted as a stringified tuple.

    Accept either a tuple (passthrough) or a string like ``"(100,)"`` /
    ``"(128,64)"`` and convert it. Anything else is returned unchanged.
    """
    if isinstance(value, (tuple, list)):
        return tuple(value)
    if isinstance(value, str) and value.startswith("(") and value.endswith(")"):
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value
        if isinstance(parsed, (tuple, list)):
            return tuple(parsed)
    return value


def _prepare_hyperparams(name: str, hyperparams: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(_DEFAULT_HYPERPARAMS.get(name, {}))
    merged.update(hyperparams or {})
    # Type-specific coercions: MLP expects a real tuple, not a string.
    if "hidden_layer_sizes" in merged:
        merged["hidden_layer_sizes"] = _coerce_tuple(merged["hidden_layer_sizes"])
    # penalty="none" is deprecated in newer sklearn; map to penalty=None.
    if merged.get("penalty") == "none":
        merged["penalty"] = None
    return merged


def _build_estimator(
    name: str,
    task3: str,
    task_class_map: dict[str, str],
    hyperparams: dict[str, Any],
) -> Any:
    dotted = task_class_map.get(task3)
    if not dotted:
        supported = list(task_class_map.keys())
        raise ValueError(
            f"model {name!r} does not support task {task3!r} (supports: {supported})"
        )
    cls = _resolve_class(dotted)
    return cls(**_prepare_hyperparams(name, hyperparams))


def _classification_metrics(
    estimator: Any, X_val: np.ndarray, y_val: pd.Series
) -> dict[str, float]:
    y_pred = estimator.predict(X_val)
    metrics: dict[str, float] = {
        "accuracy": float(accuracy_score(y_val, y_pred)),
        "f1_macro": float(f1_score(y_val, y_pred, average="macro", zero_division=0)),
    }
    if hasattr(estimator, "predict_proba"):
        try:
            proba = estimator.predict_proba(X_val)
            classes = getattr(estimator, "classes_", None)
            if proba.shape[1] == 2:
                metrics["auroc"] = float(roc_auc_score(y_val, proba[:, 1]))
            else:
                metrics["auroc"] = float(
                    roc_auc_score(y_val, proba, multi_class="ovr", average="macro")
                )
            metrics["log_loss"] = float(log_loss(y_val, proba, labels=classes))
        except (ValueError, AttributeError):
            pass
    return metrics


def _regression_metrics(
    estimator: Any, X_val: np.ndarray, y_val: pd.Series
) -> dict[str, float]:
    y_pred = estimator.predict(X_val)
    return {
        "mae": float(mean_absolute_error(y_val, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_val, y_pred))),
        "r2": float(r2_score(y_val, y_pred)),
    }


def fit_estimator(
    *,
    name: str,
    task3: str,
    task_class_map: dict[str, str],
    X_train: np.ndarray,
    y_train: pd.Series,
    X_val: np.ndarray,
    y_val: pd.Series,
    hyperparams: dict[str, Any],
) -> tuple[Any, dict[str, float], dict[str, Any]]:
    """Fit and score a bare sklearn-compatible estimator.

    Returns ``(estimator, metrics, effective_hyperparams)``. The effective dict
    is what was actually passed to the estimator constructor (library defaults
    merged with user overrides and type-coerced) so the caller can persist it
    as the ``selected_hyperparams.json`` artifact.
    """
    effective = _prepare_hyperparams(name, hyperparams)
    dotted = task_class_map.get(task3)
    if not dotted:
        supported = list(task_class_map.keys())
        raise ValueError(
            f"model {name!r} does not support task {task3!r} (supports: {supported})"
        )
    cls = _resolve_class(dotted)
    estimator = cls(**effective)
    estimator.fit(X_train, y_train)
    if task3 == "regression":
        metrics = _regression_metrics(estimator, X_val, y_val)
    else:
        metrics = _classification_metrics(estimator, X_val, y_val)
    return estimator, metrics, effective


def prepare_hyperparams(name: str, hyperparams: dict[str, Any]) -> dict[str, Any]:
    """Public wrapper around :func:`_prepare_hyperparams` for hpo.py."""
    return _prepare_hyperparams(name, hyperparams)


__all__ = ["fit_estimator", "prepare_hyperparams"]
