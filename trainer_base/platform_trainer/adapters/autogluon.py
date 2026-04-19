"""AutoGluon zero-config adapter.

Lazy-imports AutoGluon inside ``fit`` so images built without the optional
``autogluon`` extra still import this module cleanly.
"""

from __future__ import annotations

from pathlib import Path
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


def _leaderboard_to_dict(lb: pd.DataFrame) -> list[dict[str, Any]]:
    return lb.replace({np.nan: None}).to_dict(orient="records")


def _classification_metrics(predictor: Any, val_df: pd.DataFrame, target: str) -> dict[str, float]:
    y_val = val_df[target]
    X_val = val_df.drop(columns=[target])
    y_pred = predictor.predict(X_val)
    metrics: dict[str, float] = {
        "accuracy": float(accuracy_score(y_val, y_pred)),
        "f1_macro": float(f1_score(y_val, y_pred, average="macro", zero_division=0)),
    }
    try:
        proba = predictor.predict_proba(X_val)
        if isinstance(proba, pd.DataFrame):
            if proba.shape[1] == 2:
                metrics["auroc"] = float(roc_auc_score(y_val, proba.iloc[:, 1]))
            else:
                metrics["auroc"] = float(
                    roc_auc_score(y_val, proba.values, multi_class="ovr", average="macro")
                )
            metrics["log_loss"] = float(log_loss(y_val, proba.values, labels=list(proba.columns)))
    except (ValueError, AttributeError):
        pass
    return metrics


def _regression_metrics(predictor: Any, val_df: pd.DataFrame, target: str) -> dict[str, float]:
    y_val = val_df[target]
    X_val = val_df.drop(columns=[target])
    y_pred = predictor.predict(X_val)
    return {
        "mae": float(mean_absolute_error(y_val, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_val, y_pred))),
        "r2": float(r2_score(y_val, y_pred)),
    }


def fit(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    target: str,
    hyperparams: dict[str, Any],
    task: str,
    time_limit: int | None,
    presets: str | None,
    output_dir: Path | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Fit an AutoGluon TabularPredictor.

    Returns (predictor, metrics). ``metrics`` includes a ``leaderboard`` key so
    the caller can log it as a nested-run artifact table.
    """
    try:
        from autogluon.tabular import TabularPredictor  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("AutoGluon not installed in this image") from exc

    problem_type = "regression" if task == "regression" else None  # let AG infer class count
    predictor_path = str(output_dir) if output_dir is not None else None

    predictor = TabularPredictor(
        label=target,
        path=predictor_path,
        problem_type=problem_type,
    ).fit(
        train_data=train_df,
        time_limit=time_limit if time_limit and time_limit > 0 else None,
        presets=presets or "medium_quality",
        hyperparameters=hyperparams or None,
    )

    leaderboard_df = predictor.leaderboard(val_df, silent=True)

    if task == "classification":
        metrics = _classification_metrics(predictor, val_df, target)
    else:
        metrics = _regression_metrics(predictor, val_df, target)

    metrics["leaderboard"] = _leaderboard_to_dict(leaderboard_df)
    metrics["best_model"] = str(predictor.get_model_best())
    return predictor, metrics


__all__ = ["fit"]
