"""Model adapters — one per supported built-in."""

from __future__ import annotations

from typing import Any


def get_adapter(kind: str) -> Any:
    """Return the module that exposes a `fit()` for the given *kind*."""
    kind = (kind or "").lower().strip()
    if kind in ("sklearn_logistic", "sklearn_gradient_boosting"):
        from . import sklearn_like

        return sklearn_like
    if kind == "autogluon":
        from . import autogluon as autogluon_adapter

        return autogluon_adapter
    raise ValueError(f"unknown model kind: {kind!r}")


__all__ = ["get_adapter"]
