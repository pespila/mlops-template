"""Apply a user-authored TransformConfig to a pandas DataFrame."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    FunctionTransformer,
    MinMaxScaler,
    OneHotEncoder,
    OrdinalEncoder,
    StandardScaler,
)


TaskKind = Literal["classification", "regression"]


def infer_task(y: pd.Series) -> TaskKind:
    """Heuristic: numeric with many unique values => regression, else classification."""
    if pd.api.types.is_float_dtype(y) or pd.api.types.is_integer_dtype(y):
        if y.nunique(dropna=True) > 20:
            return "regression"
    return "classification"


def _log1p_transformer() -> FunctionTransformer:
    # np.log1p handles zeros; negative inputs become NaN and surface as a training-time error.
    return FunctionTransformer(func=np.log1p, feature_names_out="one-to-one", validate=False)


def _step_for_op(op: str, params: dict[str, Any]) -> Any:
    op = op.lower()
    if op in ("none", "passthrough"):
        return "passthrough"
    if op == "standard_scale":
        return StandardScaler(with_mean=params.get("with_mean", True), with_std=params.get("with_std", True))
    if op == "min_max":
        return MinMaxScaler(feature_range=tuple(params.get("feature_range", (0, 1))))
    if op == "log":
        return _log1p_transformer()
    if op == "one_hot":
        return OneHotEncoder(
            handle_unknown=params.get("handle_unknown", "ignore"),
            min_frequency=params.get("min_frequency"),
            sparse_output=False,
        )
    if op == "ordinal":
        return OrdinalEncoder(
            handle_unknown=params.get("handle_unknown", "use_encoded_value"),
            unknown_value=params.get("unknown_value", -1),
        )
    if op == "impute_median":
        return SimpleImputer(strategy="median")
    if op == "impute_mode":
        return SimpleImputer(strategy="most_frequent")
    if op == "drop":
        return "drop"
    raise ValueError(f"unknown transform op: {op!r}")


def build_column_transformer(
    transforms: list[dict[str, Any]],
    schema: dict[str, str],
) -> tuple[ColumnTransformer, list[str]]:
    """Build a ColumnTransformer from the user's declarative transforms.

    *schema* maps column name -> coarse kind ("numeric" | "categorical" | "text").
    Columns not referenced by any transform pass through unchanged.

    Returns (transformer, kept_input_columns).
    """
    grouped: dict[str, tuple[Any, list[str]]] = {}
    dropped: list[str] = []
    touched: set[str] = set()

    for idx, entry in enumerate(transforms):
        column = entry["column"]
        op = entry["op"]
        params = entry.get("params") or {}
        touched.add(column)

        step = _step_for_op(op, params)
        if step == "drop":
            dropped.append(column)
            continue

        key = f"{idx}_{op}_{column}"
        grouped[key] = (step, [column])

    all_columns = list(schema.keys())
    remainder_cols = [c for c in all_columns if c not in touched and c not in dropped]

    transformers = [(name, step, cols) for name, (step, cols) in grouped.items()]
    if remainder_cols:
        # sklearn 1.5 rejects `__` in step names — use a plain identifier.
        transformers.append(("passthrough_remainder", "passthrough", remainder_cols))

    if not transformers:
        raise ValueError("transform config produced no active columns")

    # sparse_threshold=0 to force dense output (simpler downstream serialization).
    ct = ColumnTransformer(transformers=transformers, remainder="drop", sparse_threshold=0.0)
    kept = [c for entry in transformers for c in entry[2]]
    return ct, kept


def apply_split(
    df: pd.DataFrame,
    target: str,
    split_config: dict[str, Any],
    task: TaskKind,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """Two-stage stratified split honoring {train, val, test, seed, stratify}."""
    from sklearn.model_selection import train_test_split

    train_frac = float(split_config.get("train", 0.7))
    val_frac = float(split_config.get("val", 0.15))
    test_frac = float(split_config.get("test", 0.15))
    total = train_frac + val_frac + test_frac
    if total <= 0:
        raise ValueError("split fractions sum to zero")
    train_frac, val_frac, test_frac = train_frac / total, val_frac / total, test_frac / total

    seed = int(split_config.get("seed", 42))
    stratify_flag = bool(split_config.get("stratify", task == "classification"))

    X = df.drop(columns=[target])
    y = df[target]

    strat_1 = y if (stratify_flag and task == "classification") else None
    X_tmp, X_test, y_tmp, y_test = train_test_split(
        X, y, test_size=test_frac, random_state=seed, stratify=strat_1,
    )

    val_of_remainder = val_frac / (train_frac + val_frac) if (train_frac + val_frac) > 0 else 0.0
    strat_2 = y_tmp if (stratify_flag and task == "classification") else None
    X_train, X_val, y_train, y_val = train_test_split(
        X_tmp, y_tmp, test_size=val_of_remainder, random_state=seed, stratify=strat_2,
    )
    return X_train, X_val, X_test, y_train, y_val, y_test


def coarse_schema(df: pd.DataFrame) -> dict[str, str]:
    """Map each column to 'numeric' | 'categorical' | 'text'."""
    out: dict[str, str] = {}
    for col, dtype in df.dtypes.items():
        if pd.api.types.is_numeric_dtype(dtype) and not pd.api.types.is_bool_dtype(dtype):
            out[col] = "numeric"
        elif pd.api.types.is_bool_dtype(dtype):
            out[col] = "categorical"
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            out[col] = "numeric"
        else:
            nunique = df[col].nunique(dropna=True)
            out[col] = "categorical" if nunique <= max(50, int(len(df) ** 0.5)) else "text"
    return out


__all__ = [
    "TaskKind",
    "Pipeline",
    "infer_task",
    "build_column_transformer",
    "apply_split",
    "coarse_schema",
]
