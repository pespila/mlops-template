"""Transductive clustering must fit on X_train only, score on X_val.

Before Batch 15 the DBSCAN / Agglomerative path did
``fit_predict(concat([X_train, X_val]))`` and reported metrics on the
full concatenated matrix — in-sample structure bled into the "metric".
This file guards that fix: the TransductiveClusterer's training matrix
must equal X_train (not the concat), and _internal_metrics must be
called against X_val (the held-out half).
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest


def _two_blobs(seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    a = rng.normal(loc=[0, 0], scale=0.2, size=(50, 2))
    b = rng.normal(loc=[5, 5], scale=0.2, size=(50, 2))
    X = np.vstack([a, b])
    rng.shuffle(X)
    return X[:70], X[70:]


def test_transductive_fit_uses_only_training_rows() -> None:
    from platform_trainer.adapters import clustering

    X_train, X_val = _two_blobs()

    wrapper, metrics, effective = clustering.fit_estimator(
        name="sklearn_dbscan",
        task3="clustering",
        task_class_map={"clustering": "sklearn.cluster.DBSCAN"},
        X_train=X_train,
        y_train=None,
        X_val=X_val,
        y_val=None,
        hyperparams={"eps": 0.5, "min_samples": 5},
    )

    assert isinstance(wrapper, clustering.TransductiveClusterer)
    # CRITICAL assertion: the wrapper's training matrix must be X_train,
    # NOT concat([X_train, X_val]). A regression to the old behavior would
    # produce train_X_ with shape == X_train.shape[0] + X_val.shape[0].
    assert wrapper.train_X_.shape[0] == X_train.shape[0], (
        f"regression: transductive wrapper fit on concat, got "
        f"{wrapper.train_X_.shape[0]} rows, expected {X_train.shape[0]}"
    )
    # Metrics dict must include n_clusters (sanity check that scoring ran).
    assert "n_clusters" in metrics


def test_transductive_scores_on_validation_not_training() -> None:
    """_internal_metrics must be called against X_val, not train+val concat."""
    from platform_trainer.adapters import clustering

    X_train, X_val = _two_blobs()

    # Spy on _internal_metrics to see what matrix scoring operates on.
    real_metrics = clustering._internal_metrics
    recorded: list[np.ndarray] = []

    def spy(X, labels):  # type: ignore[no-untyped-def]
        recorded.append(np.asarray(X))
        return real_metrics(X, labels)

    with patch.object(clustering, "_internal_metrics", side_effect=spy):
        clustering.fit_estimator(
            name="sklearn_dbscan",
            task3="clustering",
            task_class_map={"clustering": "sklearn.cluster.DBSCAN"},
            X_train=X_train,
            y_train=None,
            X_val=X_val,
            y_val=None,
            hyperparams={"eps": 0.5, "min_samples": 5},
        )

    assert recorded, "_internal_metrics was never called"
    scored_on = recorded[0]
    # Held-out scoring: the matrix passed to _internal_metrics must be X_val,
    # not concat([X_train, X_val]).
    assert scored_on.shape[0] == X_val.shape[0], (
        f"regression: transductive scored on {scored_on.shape[0]} rows, "
        f"expected X_val ({X_val.shape[0]})"
    )


def test_inductive_kmeans_fit_on_train_only() -> None:
    """Inductive path is the simpler case; keeps regression fence around it too."""
    from platform_trainer.adapters import clustering

    X_train, X_val = _two_blobs()
    estimator, metrics, _ = clustering.fit_estimator(
        name="sklearn_kmeans",
        task3="clustering",
        task_class_map={"clustering": "sklearn.cluster.KMeans"},
        X_train=X_train,
        y_train=None,
        X_val=X_val,
        y_val=None,
        hyperparams={"n_clusters": 2, "n_init": 5, "random_state": 0},
    )
    # KMeans exposes n_features_in_; must equal training feature count.
    assert getattr(estimator, "n_features_in_", None) == X_train.shape[1]
    assert "n_clusters" in metrics


@pytest.mark.parametrize("bad_name", ["sklearn_dbscan", "sklearn_agglomerative"])
def test_transductive_set_covers_known_bad_names(bad_name: str) -> None:
    from platform_trainer.adapters.clustering import is_transductive

    assert is_transductive(bad_name) is True
