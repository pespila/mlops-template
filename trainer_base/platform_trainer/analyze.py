"""Post-training analysis: SHAP + fairlearn bias reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _mean_abs_shap(values: Any) -> np.ndarray:
    """Normalize SHAP values (ndarray or Explanation) to a 1D mean-abs vector per feature."""
    if hasattr(values, "values"):
        arr = values.values
    else:
        arr = values
    arr = np.asarray(arr)
    if arr.ndim == 3:
        # multi-class shape (samples, features, classes) -> average across classes
        arr = np.mean(np.abs(arr), axis=(0, 2))
    elif arr.ndim == 2:
        arr = np.mean(np.abs(arr), axis=0)
    else:
        arr = np.abs(arr)
    return arr


def _save_importance_plot(importances: dict[str, float], out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    items = sorted(importances.items(), key=lambda kv: kv[1], reverse=True)[:20]
    labels = [k for k, _ in items][::-1]
    values = [v for _, v in items][::-1]

    fig, ax = plt.subplots(figsize=(7, max(3, 0.35 * len(labels))))
    ax.barh(labels, values)
    ax.set_xlabel("mean |SHAP value|")
    ax.set_title("Global feature importance")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def compute_shap(
    model: Any,
    X_sample: pd.DataFrame,
    feature_names: list[str],
    plot_path: Path = Path("/tmp/shap_global.png"),
) -> dict[str, Any]:
    """Compute SHAP values via TreeExplainer with a KernelExplainer fallback.

    ``model`` is expected to be a callable or an object exposing ``predict``
    (pipeline). The sample is assumed already aligned with ``feature_names``.
    """
    import shap  # heavyweight, imported only here

    # TreeExplainer expects the raw tree estimator — try the final step of a pipeline.
    inner = model
    if hasattr(model, "named_steps"):
        inner = model.named_steps.get("model", model)

    shap_values: Any
    try:
        explainer = shap.TreeExplainer(inner)
        # TreeExplainer works on post-transform features when the pipeline transform
        # is applied first; fall back to pipeline transform when available.
        if hasattr(model, "named_steps") and "preprocess" in getattr(model, "named_steps", {}):
            X_pre = model.named_steps["preprocess"].transform(X_sample)
        else:
            X_pre = X_sample.values if hasattr(X_sample, "values") else X_sample
        shap_values = explainer.shap_values(X_pre)
    except Exception:
        predict_fn = model.predict_proba if hasattr(model, "predict_proba") else model.predict
        background = shap.sample(X_sample, min(100, len(X_sample)), random_state=0)
        explainer = shap.KernelExplainer(predict_fn, background)
        shap_values = explainer.shap_values(X_sample, nsamples=100, silent=True)

    mean_abs = _mean_abs_shap(shap_values)
    if len(mean_abs) != len(feature_names):
        # Padded/truncated to keep the dict well-formed even when feature expansion mismatches.
        n = min(len(mean_abs), len(feature_names))
        mean_abs = mean_abs[:n]
        feature_names = feature_names[:n]
    importance = {name: float(val) for name, val in zip(feature_names, mean_abs)}

    try:
        _save_importance_plot(importance, plot_path)
    except Exception:
        pass

    sample_values: Any = shap_values
    if hasattr(sample_values, "values"):
        sample_values = sample_values.values
    sample_arr = np.asarray(sample_values)
    if sample_arr.size > 5000:  # cap payload
        sample_arr = sample_arr.reshape(-1)[:5000]

    return {
        "global_importance": importance,
        "sample_values": sample_arr.tolist(),
        "plot_path": str(plot_path),
    }


def _save_bias_plot(frame: pd.DataFrame, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(max(5, 0.8 * len(frame)), 4))
    frame.plot(kind="bar", ax=ax)
    ax.set_ylabel("metric")
    ax.set_title("Per-group metric")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def compute_bias(
    y_true: pd.Series,
    y_pred: pd.Series,
    sensitive_df: pd.DataFrame,
    metric: str = "accuracy",
    plot_path: Path = Path("/tmp/bias.png"),
) -> dict[str, Any]:
    """Fairlearn MetricFrame + demographic parity / equal opportunity (classification).

    Returns a JSON-serializable dict with per-group metrics plus deltas.
    """
    from fairlearn.metrics import (  # heavyweight
        MetricFrame,
        demographic_parity_difference,
        equalized_odds_difference,
    )
    from sklearn.metrics import accuracy_score, mean_absolute_error

    if sensitive_df is None or sensitive_df.empty:
        return {"metric": metric, "groups": {}, "deltas": {}, "plot_path": None}

    metric_fn = accuracy_score if metric == "accuracy" else mean_absolute_error

    mf = MetricFrame(
        metrics=metric_fn,
        y_true=y_true,
        y_pred=y_pred,
        sensitive_features=sensitive_df,
    )

    by_group = mf.by_group
    frame = by_group.to_frame(name=metric) if isinstance(by_group, pd.Series) else by_group
    try:
        _save_bias_plot(frame, plot_path)
    except Exception:
        pass

    deltas: dict[str, float] = {}
    try:
        deltas["demographic_parity_difference"] = float(
            demographic_parity_difference(y_true, y_pred, sensitive_features=sensitive_df)
        )
    except Exception:
        pass
    try:
        # equal_opportunity_difference is a common alias for the TPR delta; fairlearn exposes equalized_odds_difference.
        deltas["equal_opportunity_difference"] = float(
            equalized_odds_difference(y_true, y_pred, sensitive_features=sensitive_df)
        )
    except Exception:
        pass

    def _index_to_str(idx: Any) -> str:
        return "|".join(str(v) for v in idx) if isinstance(idx, tuple) else str(idx)

    groups = {_index_to_str(k): v.to_dict() if hasattr(v, "to_dict") else float(v) for k, v in frame.iterrows()}

    return {
        "metric": metric,
        "overall": float(mf.overall) if np.isscalar(mf.overall) else mf.overall.to_dict(),
        "groups": groups,
        "deltas": deltas,
        "plot_path": str(plot_path),
    }


__all__ = ["compute_shap", "compute_bias"]
