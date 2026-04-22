"""Model adapters — one module per supported fit protocol.

Dispatch is driven by the ``fit_protocol`` field on the catalog entry
(``signature_json.fit_protocol``). Valid protocols:

    sklearn          — supervised sklearn-interface estimators.
                       ``sklearn_*`` catalog names route to ``sklearn_like``;
                       ``xgboost``/``lightgbm`` route to ``boosted_trees``.
    autogluon        — AutoGluon TabularPredictor (different fit shape).
    sklearn_cluster  — sklearn clusterers (KMeans/DBSCAN/...).
    sktime           — sktime ``BaseForecaster`` wrappers.
    surprise         — Surprise recommender library (explicit feedback).
    implicit         — ``implicit`` library (implicit feedback recommenders).

If ``fit_protocol`` is missing (older catalog payloads), fall back to the
legacy name-prefix dispatch so existing runs keep working.
"""

from __future__ import annotations

from typing import Any


def get_adapter(name: str, fit_protocol: str | None = None) -> Any:
    """Return the module that exposes ``fit_estimator`` (or ``fit``) for *name*.

    Prefer the explicit ``fit_protocol`` when provided; otherwise fall back to
    dispatching on the catalog ``name`` prefix (legacy path).
    """
    name_l = (name or "").lower().strip()
    proto = (fit_protocol or "").strip().lower()

    # Explicit protocol routing -----------------------------------------------
    if proto == "sklearn" or proto == "":
        # No protocol (or legacy sklearn) — use name-prefix split to pick
        # between the plain sklearn adapter and the boosted-tree adapter.
        if name_l.startswith("sklearn_"):
            from . import sklearn_like

            return sklearn_like
        if name_l in ("xgboost", "lightgbm"):
            from . import boosted_trees

            return boosted_trees
        if name_l == "autogluon":
            # Legacy payloads may not have set fit_protocol=autogluon.
            from . import autogluon as autogluon_adapter

            return autogluon_adapter
        if proto == "":
            raise ValueError(f"unknown model name (no fit_protocol): {name_l!r}")
        raise ValueError(f"unknown sklearn-protocol model: {name_l!r}")
    if proto == "autogluon":
        from . import autogluon as autogluon_adapter

        return autogluon_adapter
    if proto == "sklearn_cluster":
        from . import clustering

        return clustering
    if proto == "sktime":
        from . import forecasting

        return forecasting
    if proto in ("surprise", "implicit"):
        from . import recommender

        return recommender
    raise ValueError(f"unknown fit_protocol: {proto!r}")


__all__ = ["get_adapter"]
