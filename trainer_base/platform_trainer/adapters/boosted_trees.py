"""XGBoost + LightGBM adapter.

Operates on already-preprocessed numpy arrays (see ``sklearn_like`` for the
rationale). Resolves the estimator class via the catalog entry's
``task_class_map`` keyed by the three-way task label.
"""

from __future__ import annotations

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

_XGB_EXTRA_DEFAULTS_CLS = {"eval_metric": "logloss", "tree_method": "hist"}
_XGB_EXTRA_DEFAULTS_REG = {"eval_metric": "rmse", "tree_method": "hist"}


def _resolve_class(dotted_path: str) -> Any:
    mod_path, _, cls_name = dotted_path.rpartition(".")
    if not mod_path:
        raise ValueError(f"invalid dotted class path: {dotted_path!r}")
    mod = importlib.import_module(mod_path)
    return getattr(mod, cls_name)


def _prepare_hyperparams(
    name: str, task3: str, hyperparams: dict[str, Any]
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if name == "xgboost":
        merged.update(
            _XGB_EXTRA_DEFAULTS_REG if task3 == "regression" else _XGB_EXTRA_DEFAULTS_CLS
        )
    merged.update(hyperparams or {})
    return merged


def _encode_labels(
    task3: str, y_train: pd.Series, y_val: pd.Series
) -> tuple[pd.Series, pd.Series, Any | None]:
    if task3 == "regression":
        return y_train, y_val, None
    if pd.api.types.is_numeric_dtype(y_train) and not pd.api.types.is_bool_dtype(y_train):
        return y_train, y_val, None
    from sklearn.preprocessing import LabelEncoder

    enc = LabelEncoder()
    enc.fit(pd.concat([y_train, y_val], ignore_index=True))
    return (
        pd.Series(enc.transform(y_train), index=y_train.index),
        pd.Series(enc.transform(y_val), index=y_val.index),
        enc,
    )


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
            if proba.shape[1] == 2:
                metrics["auroc"] = float(roc_auc_score(y_val, proba[:, 1]))
            else:
                metrics["auroc"] = float(
                    roc_auc_score(y_val, proba, multi_class="ovr", average="macro")
                )
            metrics["log_loss"] = float(log_loss(y_val, proba))
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
) -> tuple[Any, dict[str, float], dict[str, Any], Any | None]:
    """Fit a bare XGBoost/LightGBM estimator on pre-transformed inputs.

    Returns ``(estimator, metrics, effective_hyperparams, label_encoder)``.
    The encoder is returned so the caller can attach it to the final Pipeline
    for serving/analyze to ``inverse_transform`` integer class predictions.
    """
    effective = _prepare_hyperparams(name, task3, hyperparams)
    dotted = task_class_map.get(task3)
    if not dotted:
        supported = list(task_class_map.keys())
        raise ValueError(
            f"model {name!r} does not support task {task3!r} (supports: {supported})"
        )
    cls = _resolve_class(dotted)
    y_train_fit, y_val_fit, encoder = _encode_labels(task3, y_train, y_val)
    estimator = cls(**effective)
    estimator.fit(X_train, y_train_fit)
    if task3 == "regression":
        metrics = _regression_metrics(estimator, X_val, y_val_fit)
    else:
        metrics = _classification_metrics(estimator, X_val, y_val_fit)
    return estimator, metrics, effective, encoder


def prepare_hyperparams(
    name: str, task3: str, hyperparams: dict[str, Any]
) -> dict[str, Any]:
    """Public wrapper around :func:`_prepare_hyperparams` for hpo.py."""
    return _prepare_hyperparams(name, task3, hyperparams)


def encode_labels(
    task3: str, y_train: pd.Series, y_val: pd.Series
) -> tuple[pd.Series, pd.Series, Any | None]:
    """Public wrapper around :func:`_encode_labels` for hpo.py."""
    return _encode_labels(task3, y_train, y_val)


__all__ = ["fit_estimator", "prepare_hyperparams", "encode_labels"]
