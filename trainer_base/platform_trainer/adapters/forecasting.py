"""Adapter for sktime-based univariate forecasters.

Forecasting departs from the supervised preprocessor-once pipeline:

* **Input**: a pandas Series indexed by time (the user's time column becomes
  a DatetimeIndex / PeriodIndex) holding the value to forecast.
* **No ColumnTransformer**: the trainer calls into this adapter with the
  prepared Series directly — there's no feature matrix to scale/encode.
* **Split**: temporal holdout (last ``val_frac`` rows → test). Random splits
  leak future-into-past information for time series.
* **Metrics**: MAE, RMSE, sMAPE on the holdout. All minimize-is-better.

All five catalog models share the sktime ``BaseForecaster`` contract
(``fit(y, fh=...)``, ``predict(fh)``). The adapter flattens SARIMAX tuple
hyperparams (order / seasonal_order) into individual integer knobs so the
wizard's flat hyperparam schema can still express them.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _require_sktime() -> None:
    """Loudly surface a missing sktime install with a self-describing message.

    Without this, a bare ``ModuleNotFoundError: sktime`` bubbles up — which
    leaves the user to reverse-engineer that the trainer image wasn't rebuilt
    with the ``[forecasting]`` extras. The explicit RuntimeError makes the
    failure mode obvious in the run logs.
    """
    try:
        import sktime  # noqa: F401
    except ImportError as exc:  # pragma: no cover — install-dependent branch
        raise RuntimeError(
            "sktime is not installed in this trainer image. Rebuild the base "
            "trainer with `pip install '.[forecasting,recommender]'` "
            "(see trainer_base/Dockerfile)."
        ) from exc


def _resolve_forecaster(name: str, hyperparams: dict[str, Any]) -> Any:
    """Build a sktime forecaster instance for the given catalog ``name``.

    sktime is imported lazily because the supervised trainer image doesn't
    ship it — only the forecasting serving image does. Attempting to import
    at module load would break every other family's trainer.
    """
    _require_sktime()
    name_l = (name or "").strip().lower()

    if name_l == "sktime_naive":
        from sktime.forecasting.naive import NaiveForecaster

        strategy = hyperparams.get("strategy") or "last"
        sp = int(hyperparams.get("sp", 1))
        return NaiveForecaster(strategy=strategy, sp=sp)

    if name_l == "sktime_theta":
        from sktime.forecasting.theta import ThetaForecaster

        sp = int(hyperparams.get("sp", 1))
        deseasonalize = bool(hyperparams.get("deseasonalize", True))
        return ThetaForecaster(sp=sp, deseasonalize=deseasonalize)

    if name_l == "sktime_ets":
        from sktime.forecasting.exp_smoothing import ExponentialSmoothing

        trend = hyperparams.get("trend") or None
        seasonal = hyperparams.get("seasonal") or None
        sp = int(hyperparams.get("sp", 1))
        damped_trend = bool(hyperparams.get("damped_trend", False))
        return ExponentialSmoothing(
            trend=trend or None,
            seasonal=seasonal or None,
            sp=sp,
            damped_trend=damped_trend,
        )

    if name_l == "sktime_arima":
        # Flattened order = (p, d, q).
        from sktime.forecasting.arima import ARIMA

        order = (
            int(hyperparams.get("p", 1)),
            int(hyperparams.get("d", 0)),
            int(hyperparams.get("q", 0)),
        )
        return ARIMA(order=order, suppress_warnings=True)

    if name_l == "sktime_sarimax":
        from sktime.forecasting.arima import ARIMA

        order = (
            int(hyperparams.get("p", 1)),
            int(hyperparams.get("d", 0)),
            int(hyperparams.get("q", 0)),
        )
        seasonal_order = (
            int(hyperparams.get("P", 0)),
            int(hyperparams.get("D", 0)),
            int(hyperparams.get("Q", 0)),
            int(hyperparams.get("s", 0)),
        )
        return ARIMA(
            order=order,
            seasonal_order=seasonal_order,
            suppress_warnings=True,
        )

    raise ValueError(f"unknown forecasting model: {name_l!r}")


def _smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Symmetric MAPE — ``100 * mean(|a-f| / ((|a|+|f|)/2))`` with zero guard."""
    num = np.abs(y_true - y_pred)
    den = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    den = np.where(den == 0, 1e-12, den)
    return float(100.0 * np.mean(num / den))


def _forecast_metrics(y_true: pd.Series, y_pred: pd.Series) -> dict[str, float]:
    y_true_np = np.asarray(y_true, dtype=float)
    y_pred_np = np.asarray(y_pred, dtype=float)
    if y_true_np.shape != y_pred_np.shape:
        # sktime sometimes emits a frame; flatten both.
        y_true_np = y_true_np.reshape(-1)
        y_pred_np = y_pred_np.reshape(-1)
    err = y_true_np - y_pred_np
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    return {
        "mae": mae,
        "rmse": rmse,
        "smape": _smape(y_true_np, y_pred_np),
    }


def fit_estimator(
    *,
    name: str,
    task3: str,
    task_class_map: dict[str, str],
    X_train: Any,
    y_train: pd.Series,
    X_val: Any,
    y_val: pd.Series,
    hyperparams: dict[str, Any],
) -> tuple[Any, dict[str, float], dict[str, Any]]:
    """Fit a sktime forecaster on ``y_train`` and score on ``y_val``.

    ``X_train`` / ``X_val`` are either ``None`` (univariate) or exogenous
    DataFrames; the current catalog doesn't expose exogenous covariates but
    the contract leaves room for them.

    Returns ``(forecaster, metrics, effective_hyperparams)``. The forecaster
    is pickled directly for serving — sktime forecasters pickle cleanly.
    """
    _ = task3  # always "forecasting" here; kept for signature parity
    _ = task_class_map
    forecaster = _resolve_forecaster(name, hyperparams or {})

    if not isinstance(y_train, pd.Series):
        y_train = pd.Series(y_train)
    y_val_s = y_val if isinstance(y_val, pd.Series) else pd.Series(y_val)

    # Belt-and-suspenders: if the caller forgot to assign a freq to the
    # DatetimeIndex (statsmodels + sktime both require one for .predict),
    # infer it here or fall back to "D". The orchestrator already does this
    # defensively in _run_forecasting, but the adapter stays usable on its
    # own when exercised from tests or a future HPO loop.
    for series_ref in (y_train, y_val_s):
        idx = series_ref.index
        if isinstance(idx, pd.DatetimeIndex) and idx.freq is None:
            try:
                series_ref.index.freq = pd.infer_freq(idx)  # type: ignore[misc]
            except Exception:  # noqa: BLE001
                pass
            if series_ref.index.freq is None:
                series_ref.index.freq = "D"  # type: ignore[misc]

    forecaster.fit(y_train, X=X_train)

    # Forecast horizon = length of the validation block. sktime accepts a
    # relative fh (ForecastingHorizon from 1..N) against the training end.
    from sktime.forecasting.base import ForecastingHorizon

    fh = ForecastingHorizon(list(range(1, len(y_val_s) + 1)), is_relative=True)
    y_pred = forecaster.predict(fh=fh, X=X_val)
    metrics = _forecast_metrics(y_val_s, y_pred)

    effective = {str(k): v for k, v in (hyperparams or {}).items()}
    return forecaster, metrics, effective


def prepare_hyperparams(name: str, hyperparams: dict[str, Any]) -> dict[str, Any]:
    """Public no-op passthrough — sktime wrappers accept the flat dict as-is."""
    _ = name
    return dict(hyperparams or {})


__all__ = ["fit_estimator", "prepare_hyperparams"]
