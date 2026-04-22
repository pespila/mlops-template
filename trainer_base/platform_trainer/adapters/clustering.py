"""Adapter for sklearn clusterers.

Clustering is unsupervised — there is no target column, no train/val split
in the supervised sense. The trainer's clustering branch fits the
ColumnTransformer on the selected feature columns (no ``y``), then calls
into this adapter with the transformed matrix.

Two serving modes live here:

* **inductive**  — estimator exposes ``.predict(X)`` (KMeans, MiniBatchKMeans,
  GaussianMixture). We return the bare estimator; ``__main__.py`` wraps it in
  a ``Pipeline(preprocessor, estimator)`` and joblib-dumps.

* **transductive** — estimator has only ``.fit_predict(X)``; no natural
  out-of-sample prediction (DBSCAN, AgglomerativeClustering). We return a
  wrapper :class:`TransductiveClusterer` that carries the fitted training
  matrix + its labels and implements ``.predict`` via 1-NN assignment. This
  keeps a uniform contract for the serving layer (``model.predict(X)``)
  without silently pretending DBSCAN is inductive.

Metrics computed: silhouette score (maximize), Calinski-Harabasz (maximize),
Davies-Bouldin (minimize). All internal metrics — no ground truth required.
"""

from __future__ import annotations

import importlib
from typing import Any

import numpy as np
from sklearn.metrics import (
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)


# Models whose .predict is unreliable / absent — serve via 1-NN assignment.
_TRANSDUCTIVE = {"sklearn_dbscan", "sklearn_agglomerative"}


class TransductiveClusterer:
    """Wraps a fit_predict-only clusterer so it exposes ``.predict``.

    ``predict`` runs a brute-force nearest-neighbor lookup against the
    training matrix and returns the training point's cluster label. This is
    an approximation, not an inductive model — document it honestly in the
    UI and serving README.
    """

    def __init__(self, estimator: Any, train_X: np.ndarray, train_labels: np.ndarray):
        self.estimator = estimator
        self.train_X_ = np.asarray(train_X)
        self.train_labels_ = np.asarray(train_labels)

    def predict(self, X: Any) -> np.ndarray:
        from sklearn.neighbors import NearestNeighbors

        if not hasattr(self, "_nn"):
            # Lazy-build the NN index the first time predict is called. After
            # joblib.dump → joblib.load the index is rebuilt on first use.
            self._nn = NearestNeighbors(n_neighbors=1).fit(self.train_X_)
        X_arr = np.asarray(X)
        if X_arr.ndim == 1:
            X_arr = X_arr.reshape(1, -1)
        _, idx = self._nn.kneighbors(X_arr, n_neighbors=1)
        return self.train_labels_[idx[:, 0]]

    def fit_predict(self, X: Any) -> np.ndarray:
        # Provided for symmetry; in practice we fit in the adapter, not here.
        labels = self.estimator.fit_predict(X)
        self.train_X_ = np.asarray(X)
        self.train_labels_ = np.asarray(labels)
        return labels


def _resolve_class(dotted_path: str) -> Any:
    mod_path, _, cls_name = dotted_path.rpartition(".")
    if not mod_path:
        raise ValueError(f"invalid dotted class path: {dotted_path!r}")
    mod = importlib.import_module(mod_path)
    return getattr(mod, cls_name)


def _prepare_hyperparams(name: str, hyperparams: dict[str, Any]) -> dict[str, Any]:
    merged = dict(hyperparams or {})
    # DBSCAN eps needs a float — guard against the wizard shipping an int.
    if name == "sklearn_dbscan" and "eps" in merged:
        merged["eps"] = float(merged["eps"])
    return merged


def _internal_metrics(X: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    """Compute silhouette / CH / DB, guarding against degenerate partitions.

    Silhouette requires at least 2 clusters and at least 2 points per cluster.
    DBSCAN can emit ``-1`` for noise; we exclude those points before scoring
    so a cluster of outliers doesn't dominate.
    """
    out: dict[str, float] = {"n_clusters": float(len(set(labels.tolist())))}
    mask = labels != -1
    X_eff = X[mask]
    L_eff = labels[mask]
    unique = set(L_eff.tolist())
    if len(unique) < 2 or len(L_eff) < 2:
        # Can't score a single-cluster partition — leave metric fields empty.
        return out
    try:
        out["silhouette"] = float(silhouette_score(X_eff, L_eff))
    except Exception:  # noqa: BLE001 — sklearn raises ValueError on bad inputs
        pass
    try:
        out["calinski_harabasz"] = float(calinski_harabasz_score(X_eff, L_eff))
    except Exception:  # noqa: BLE001
        pass
    try:
        out["davies_bouldin"] = float(davies_bouldin_score(X_eff, L_eff))
    except Exception:  # noqa: BLE001
        pass
    return out


def fit_estimator(
    *,
    name: str,
    task3: str,
    task_class_map: dict[str, str],
    X_train: np.ndarray,
    y_train: Any,
    X_val: np.ndarray,
    y_val: Any,
    hyperparams: dict[str, Any],
) -> tuple[Any, dict[str, float], dict[str, Any]]:
    """Fit a clusterer on training data and score on the validation matrix.

    ``task3`` is always ``"clustering"`` here but the parameter is kept for
    uniform signature with the supervised adapters. ``y_*`` arguments are
    ignored (clustering is unsupervised).

    Inductive (KMeans, GMM, MiniBatchKMeans): fit on ``X_train``, predict on
    ``X_val``, score on the predictions. Returns the bare estimator.

    Transductive (DBSCAN, Agglomerative): fit on ``X_train`` only, then
    project ``X_val`` into cluster labels via 1-NN against the fit matrix
    and score on that held-out assignment. Returns a
    :class:`TransductiveClusterer`. Prior behavior fit on
    ``concat([X_train, X_val])`` and scored on the same matrix — that
    mixed in-sample structure into the "metric" and made transductive
    silhouette/CH/DB not comparable to the inductive path.
    """
    dotted = task_class_map.get(task3) or task_class_map.get("clustering")
    if not dotted:
        raise ValueError(
            f"model {name!r} has no clustering class in task_class_map "
            f"(got {list(task_class_map.keys())})"
        )
    cls = _resolve_class(dotted)
    effective = _prepare_hyperparams(name, hyperparams)

    X_train_np = np.asarray(X_train)
    X_val_np = np.asarray(X_val) if X_val is not None else None
    has_val = X_val_np is not None and len(X_val_np) > 0

    if name in _TRANSDUCTIVE:
        base = cls(**effective)
        if hasattr(base, "fit_predict"):
            train_labels = np.asarray(base.fit_predict(X_train_np))
        else:
            base.fit(X_train_np)
            train_labels = np.asarray(getattr(base, "labels_", None))
            if train_labels is None:
                raise RuntimeError(f"{name!r} produced no labels_ after fit")
        wrapper = TransductiveClusterer(
            estimator=base, train_X=X_train_np, train_labels=train_labels
        )
        if has_val:
            val_labels = np.asarray(wrapper.predict(X_val_np))
            metrics = _internal_metrics(X_val_np, val_labels)
        else:
            metrics = _internal_metrics(X_train_np, train_labels)
        return wrapper, metrics, effective

    estimator = cls(**effective)
    estimator.fit(X_train_np)
    if has_val:
        preds = estimator.predict(X_val_np)
        metrics = _internal_metrics(X_val_np, np.asarray(preds))
    else:
        preds = estimator.predict(X_train_np)
        metrics = _internal_metrics(X_train_np, np.asarray(preds))
    return estimator, metrics, effective


def prepare_hyperparams(name: str, hyperparams: dict[str, Any]) -> dict[str, Any]:
    """Public wrapper for :mod:`platform_trainer.hpo` consumption."""
    return _prepare_hyperparams(name, hyperparams)


def is_transductive(name: str) -> bool:
    return name in _TRANSDUCTIVE


__all__ = [
    "TransductiveClusterer",
    "fit_estimator",
    "is_transductive",
    "prepare_hyperparams",
]
