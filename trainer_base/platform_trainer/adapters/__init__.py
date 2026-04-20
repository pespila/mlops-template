"""Model adapters — one module per supported framework.

Dispatch by catalog entry name. Any ``sklearn_*`` family routes to the unified
sklearn_like adapter; xgboost / lightgbm route to boosted_trees; autogluon
routes to the autogluon adapter (which has a different calling convention —
see its module docstring).
"""

from __future__ import annotations

from typing import Any


def get_adapter(name: str) -> Any:
    """Return the module that exposes ``fit_estimator`` (or ``fit`` for AG) for *name*."""
    name = (name or "").lower().strip()
    if name.startswith("sklearn_"):
        from . import sklearn_like

        return sklearn_like
    if name in ("xgboost", "lightgbm"):
        from . import boosted_trees

        return boosted_trees
    if name == "autogluon":
        from . import autogluon as autogluon_adapter

        return autogluon_adapter
    raise ValueError(f"unknown model name: {name!r}")


__all__ = ["get_adapter"]
