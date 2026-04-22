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

from platform_trainer.feature_engineering import DateFeatureExpander

TaskKind = Literal["classification", "regression"]
TaskKind3 = Literal["regression", "binary_classification", "multiclass_classification"]


def infer_task(y: pd.Series) -> TaskKind:
    """Heuristic: numeric with many unique values => regression, else classification.

    Kept on the two-way enum so existing adapters stay untouched; use
    :func:`infer_task_3way` when the caller needs binary/multiclass distinction
    (recommendation UI, HPO metric selection).
    """
    if pd.api.types.is_float_dtype(y) or pd.api.types.is_integer_dtype(y):
        if y.nunique(dropna=True) > 20:
            return "regression"
    return "classification"


def infer_task_3way(y: pd.Series) -> TaskKind3:
    """Return regression / binary_classification / multiclass_classification.

    Uses the same numeric-cardinality heuristic as :func:`infer_task` for the
    regression boundary, then splits the classification bucket by class count.
    """
    if pd.api.types.is_float_dtype(y) or pd.api.types.is_integer_dtype(y):
        if y.nunique(dropna=True) > 20:
            return "regression"
    n_classes = y.nunique(dropna=True)
    return "binary_classification" if n_classes <= 2 else "multiclass_classification"


def coarse_task(task: str) -> TaskKind:
    """Map a three-way task label back to the two-way enum used by adapters."""
    if task == "regression":
        return "regression"
    return "classification"


def _log1p_transformer() -> FunctionTransformer:
    # np.log1p handles zeros; negative inputs become NaN and surface as a training-time error.
    return FunctionTransformer(
        func=np.log1p, feature_names_out="one-to-one", validate=False
    )


def _step_for_op(op: str, params: dict[str, Any]) -> Any:
    op = op.lower()
    if op in ("none", "passthrough"):
        return "passthrough"
    if op == "standard_scale":
        return StandardScaler(
            with_mean=params.get("with_mean", True),
            with_std=params.get("with_std", True),
        )
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
    if op == "label":
        # For per-feature encoding, sklearn's LabelEncoder is target-only;
        # OrdinalEncoder wrapped around a single column is the semantic
        # equivalent (one integer per category).
        return OrdinalEncoder(
            handle_unknown=params.get("handle_unknown", "use_encoded_value"),
            unknown_value=params.get("unknown_value", -1),
        )
    if op == "date_features":
        return Pipeline(
            steps=[
                ("expand", DateFeatureExpander()),
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
            ]
        )
    if op == "impute_mean":
        return SimpleImputer(strategy="mean")
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

    # Smart defaults for any column the user didn't explicitly transform:
    #   numeric    -> passthrough
    #   categorical-> one-hot (handle_unknown=ignore so new categories at
    #                 inference time don't blow up)
    #   boolean    -> passthrough
    #   datetime   -> expand to year/month/day/dow/quarter[/hour] then scale
    #   text       -> drop (high-cardinality strings aren't tree-friendly;
    #                 a proper vectorizer is a v1 feature)
    if remainder_cols:
        numeric_default = [
            c for c in remainder_cols if schema.get(c) in ("numeric", "boolean")
        ]
        categorical_default = [
            c for c in remainder_cols if schema.get(c) == "categorical"
        ]
        datetime_default = [c for c in remainder_cols if schema.get(c) == "datetime"]
        # text columns fall into neither bucket → implicitly dropped
        if numeric_default:
            transformers.append(("auto_passthrough", "passthrough", numeric_default))
        if categorical_default:
            transformers.append(
                (
                    "auto_onehot",
                    OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                    categorical_default,
                )
            )
        for col in datetime_default:
            transformers.append(
                (
                    f"auto_datefeat_{col}",
                    Pipeline(
                        steps=[
                            ("expand", DateFeatureExpander()),
                            ("impute", SimpleImputer(strategy="median")),
                            ("scale", StandardScaler()),
                        ]
                    ),
                    [col],
                )
            )

    if not transformers:
        raise ValueError("transform config produced no active columns")

    # sparse_threshold=0 to force dense output (simpler downstream serialization).
    ct = ColumnTransformer(
        transformers=transformers, remainder="drop", sparse_threshold=0.0
    )
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
    train_frac, val_frac, test_frac = (
        train_frac / total,
        val_frac / total,
        test_frac / total,
    )

    seed = int(split_config.get("seed", 42))
    stratify_flag = bool(split_config.get("stratify", task == "classification"))

    X = df.drop(columns=[target])
    y = df[target]

    strat_1 = y if (stratify_flag and task == "classification") else None
    X_tmp, X_test, y_tmp, y_test = train_test_split(
        X,
        y,
        test_size=test_frac,
        random_state=seed,
        stratify=strat_1,
    )

    val_of_remainder = (
        val_frac / (train_frac + val_frac) if (train_frac + val_frac) > 0 else 0.0
    )
    strat_2 = y_tmp if (stratify_flag and task == "classification") else None
    X_train, X_val, y_train, y_val = train_test_split(
        X_tmp,
        y_tmp,
        test_size=val_of_remainder,
        random_state=seed,
        stratify=strat_2,
    )
    return X_train, X_val, X_test, y_train, y_val, y_test


_VALID_USER_SEMANTICS = {"numeric", "categorical", "datetime", "text", "boolean"}


def coarse_schema(
    df: pd.DataFrame,
    user_types: dict[str, str] | None = None,
) -> dict[str, str]:
    """Map each column to 'numeric' | 'categorical' | 'datetime' | 'text'.

    When *user_types* is provided, any column present there overrides the
    dtype-based inference — this is how a string-stored date column the
    user flagged as ``datetime`` reaches the date-feature expander even
    though pandas read it as ``object``.
    """
    user_types = user_types or {}
    out: dict[str, str] = {}
    for col, dtype in df.dtypes.items():
        override = user_types.get(str(col))
        if override in _VALID_USER_SEMANTICS:
            # "boolean" collapses into "categorical" for the preprocessor
            # (same one-hot default); everything else is passed through.
            out[col] = "categorical" if override == "boolean" else override
            continue
        if pd.api.types.is_numeric_dtype(dtype) and not pd.api.types.is_bool_dtype(
            dtype
        ):
            out[col] = "numeric"
        elif pd.api.types.is_bool_dtype(dtype):
            out[col] = "categorical"
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            out[col] = "datetime"
        else:
            nunique = df[col].nunique(dropna=True)
            out[col] = (
                "categorical" if nunique <= max(50, int(len(df) ** 0.5)) else "text"
            )
    return out


__all__ = [
    "Pipeline",
    "TaskKind",
    "TaskKind3",
    "apply_split",
    "build_column_transformer",
    "coarse_schema",
    "coarse_task",
    "infer_task",
    "infer_task_3way",
]
