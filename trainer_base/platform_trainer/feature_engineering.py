"""Feature-engineering transformers used by :mod:`transforms`.

Currently:

* :class:`DateFeatureExpander` — turn one parsed-or-parseable datetime
  column into ``{col}_year``, ``{col}_month``, ``{col}_day``,
  ``{col}_dow`` (day of week 0-6), ``{col}_quarter`` and, only when any
  sampled value has a non-zero time-of-day, ``{col}_hour``.

The expander is single-column by design so it can live inside a
``ColumnTransformer`` branch alongside scalers and encoders for other
columns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin


class DateFeatureExpander(BaseEstimator, TransformerMixin):
    _BASE_FEATURES = ("year", "month", "day", "dow", "quarter")

    def __init__(self, sample_limit: int = 500) -> None:
        self.sample_limit = sample_limit
        self.include_hour_: bool = False
        self.feature_names_: list[str] = []
        self.input_column_: str | None = None

    def _to_datetime(self, X: pd.DataFrame | pd.Series | np.ndarray) -> pd.Series:
        if isinstance(X, pd.DataFrame):
            if X.shape[1] != 1:
                raise ValueError("DateFeatureExpander expects exactly one input column")
            series = X.iloc[:, 0]
        elif isinstance(X, pd.Series):
            series = X
        else:
            series = pd.Series(np.asarray(X).ravel())
        return pd.to_datetime(series, errors="coerce")

    def fit(self, X, y=None):  # noqa: D401 — sklearn API
        if isinstance(X, pd.DataFrame) and X.shape[1] == 1:
            self.input_column_ = str(X.columns[0])
        parsed = self._to_datetime(X)
        sample = parsed.dropna().head(self.sample_limit)
        self.include_hour_ = bool(
            len(sample)
            and (
                (sample.dt.hour != 0).any()
                or (sample.dt.minute != 0).any()
                or (sample.dt.second != 0).any()
            )
        )
        prefix = self.input_column_ or "date"
        self.feature_names_ = [f"{prefix}_{name}" for name in self._BASE_FEATURES]
        if self.include_hour_:
            self.feature_names_.append(f"{prefix}_hour")
        return self

    def transform(self, X):
        parsed = self._to_datetime(X)
        parts: dict[str, np.ndarray] = {
            "year": parsed.dt.year.to_numpy(),
            "month": parsed.dt.month.to_numpy(),
            "day": parsed.dt.day.to_numpy(),
            "dow": parsed.dt.dayofweek.to_numpy(),
            "quarter": parsed.dt.quarter.to_numpy(),
        }
        if self.include_hour_:
            parts["hour"] = parsed.dt.hour.to_numpy()

        cols = [parts[name] for name in self._BASE_FEATURES]
        if self.include_hour_:
            cols.append(parts["hour"])
        arr = np.vstack(cols).T.astype("float64")
        # NaT → NaN propagates through dt accessors → imputed downstream.
        return arr

    def get_feature_names_out(self, input_features=None):  # noqa: D401 — sklearn API
        return np.asarray(self.feature_names_, dtype=object)


__all__ = ["DateFeatureExpander"]
