"""XGBoost + LightGBM adapter. Lazy imports."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline


def _estimator(kind: str, task: str, hyperparams: dict[str, Any]) -> Any:
    kind = kind.lower()
    if kind == "xgboost":
        from xgboost import XGBClassifier, XGBRegressor

        cls = XGBClassifier if task == "classification" else XGBRegressor
        defaults = {"eval_metric": "logloss" if task == "classification" else "rmse",
                    "tree_method": "hist"}
        defaults.update(hyperparams or {})
        return cls(**defaults)
    if kind == "lightgbm":
        from lightgbm import LGBMClassifier, LGBMRegressor

        cls = LGBMClassifier if task == "classification" else LGBMRegressor
        return cls(**(hyperparams or {}))
    raise ValueError(f"boosted_trees does not support kind {kind!r}")


def _classification_metrics(estimator: Any, X_val: Any, y_val: Any) -> dict[str, float]:
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
                metrics["auroc"] = float(roc_auc_score(y_val, proba, multi_class="ovr", average="macro"))
            metrics["log_loss"] = float(log_loss(y_val, proba))
        except (ValueError, AttributeError):
            pass
    return metrics


def _regression_metrics(estimator: Any, X_val: Any, y_val: Any) -> dict[str, float]:
    y_pred = estimator.predict(X_val)
    return {
        "mae": float(mean_absolute_error(y_val, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_val, y_pred))),
        "r2": float(r2_score(y_val, y_pred)),
    }


def _encode_labels(kind: str, task: str, y_train: pd.Series, y_val: pd.Series):  # type: ignore[no-untyped-def]
    """XGBoost + LightGBM classifiers require numeric class labels.

    Returns (y_train_enc, y_val_enc, encoder_or_none). Encoder is attached to
    the pipeline so downstream metric + prediction code can decode.
    """
    if task != "classification":
        return y_train, y_val, None
    if pd.api.types.is_numeric_dtype(y_train) and not pd.api.types.is_bool_dtype(y_train):
        return y_train, y_val, None
    from sklearn.preprocessing import LabelEncoder

    enc = LabelEncoder()
    enc.fit(pd.concat([y_train, y_val], ignore_index=True))
    return pd.Series(enc.transform(y_train), index=y_train.index), pd.Series(
        enc.transform(y_val), index=y_val.index
    ), enc


def fit(
    kind: str,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    hyperparams: dict[str, Any],
    task: str,
    preprocessor: ColumnTransformer,
) -> tuple[Pipeline, dict[str, float]]:
    y_train_fit, y_val_fit, encoder = _encode_labels(kind, task, y_train, y_val)
    estimator = _estimator(kind, task, hyperparams)
    pipeline = Pipeline(steps=[("preprocess", preprocessor), ("model", estimator)])
    pipeline.fit(X_train, y_train_fit)
    if encoder is not None:
        # Expose decoder on the pipeline so serving + analyze can inverse_transform.
        pipeline.label_encoder_ = encoder  # type: ignore[attr-defined]
    if task == "classification":
        metrics = _classification_metrics(pipeline, X_val, y_val_fit)
    else:
        metrics = _regression_metrics(pipeline, X_val, y_val_fit)
    return pipeline, metrics


__all__ = ["fit"]
