"""Adapter for collaborative-filtering recommenders.

Handles two distinct fit protocols behind a single serving-facing contract:

* ``surprise`` (SVD / SVD++ / KNN / NMF) — explicit feedback. Metrics: RMSE,
  MAE on a random held-out slice of the interactions frame.
* ``implicit`` (AlternatingLeastSquares) — implicit feedback. Needs a CSR
  confidence matrix keyed by ``(user_index, item_index)`` with entries
  ``1 + alpha * rating``. Metrics: Precision@K, Recall@K, NDCG@K via
  user-holdout (last-interaction per user).

The trainer passes the interactions frame as a *hyperparameter*
(``_interactions``) because recommender fit signatures don't align with the
supervised ``(X_train, y_train)`` shape. Private keys prefixed ``_`` are
stripped out before persisting effective hyperparams.

All fitted models are wrapped in :class:`RecommenderWrapper` which exposes
a uniform ``predict_one(user_id, item_id) -> float`` and
``top_k(user_id, k) -> list[item_id]``. Serving's generated ``predict.py``
calls these methods regardless of which library trained the model.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd


logger = logging.getLogger("platform_trainer.recommender")


class RecommenderWrapper:
    """Uniform inference surface over Surprise / implicit fitted models.

    Stores the original ``user_id`` / ``item_id`` domain in two id-maps so
    serving callers can hand in the raw ids from their dataset without
    knowing the encoded internal indices.
    """

    def __init__(
        self,
        *,
        backend: str,
        model: Any,
        user_to_idx: dict[Any, int],
        item_to_idx: dict[Any, int],
        idx_to_item: list[Any],
        user_items: dict[int, set[int]] | None = None,
        confidence: Any = None,
    ):
        self.backend = backend
        self.model = model
        self.user_to_idx = user_to_idx
        self.item_to_idx = item_to_idx
        self.idx_to_item = idx_to_item
        # Items already consumed by each user — used to filter them out of
        # top-K recommendations on the implicit path.
        self.user_items = user_items or {}
        # Sparse confidence matrix (implicit backend only). Pickled with
        # joblib — scipy sparse matrices serialize cleanly.
        self.confidence = confidence

    def predict_one(self, user_id: Any, item_id: Any) -> float:
        if self.backend == "surprise":
            pred = self.model.predict(str(user_id), str(item_id))
            return float(getattr(pred, "est", 0.0))
        # implicit: inner product of user + item factors
        u_idx = self.user_to_idx.get(user_id)
        i_idx = self.item_to_idx.get(item_id)
        if u_idx is None or i_idx is None:
            return 0.0
        uf = self.model.user_factors[u_idx]
        iv = self.model.item_factors[i_idx]
        return float(np.dot(uf, iv))

    def top_k(self, user_id: Any, k: int = 10) -> list[Any]:
        k = int(k)
        if self.backend == "surprise":
            # Surprise has no native top-K; fall back to predicting every
            # catalog item and sorting. Fine for the small movielens-scale
            # datasets this serves — not a production recommender.
            seen = self.user_items.get(self.user_to_idx.get(user_id, -1), set())
            scored: list[tuple[float, Any]] = []
            for idx, item in enumerate(self.idx_to_item):
                if idx in seen:
                    continue
                pred = self.model.predict(str(user_id), str(item))
                scored.append((float(getattr(pred, "est", 0.0)), item))
            scored.sort(key=lambda t: t[0], reverse=True)
            return [item for _score, item in scored[:k]]

        # implicit backend: use the library's own recommend().
        u_idx = self.user_to_idx.get(user_id)
        if u_idx is None:
            return []
        ids, _scores = self.model.recommend(
            u_idx,
            self.confidence[u_idx],
            N=k,
            filter_already_liked_items=True,
        )
        return [self.idx_to_item[int(i)] for i in ids]


# -- Surprise path ----------------------------------------------------------


def _build_surprise(name: str, hyperparams: dict[str, Any]) -> Any:
    name_l = name.strip().lower()
    if name_l == "surprise_svd":
        from surprise import SVD  # type: ignore[import]

        return SVD(
            n_factors=int(hyperparams.get("n_factors", 100)),
            n_epochs=int(hyperparams.get("n_epochs", 20)),
            lr_all=float(hyperparams.get("lr_all", 0.005)),
            reg_all=float(hyperparams.get("reg_all", 0.02)),
        )
    if name_l == "surprise_svdpp":
        from surprise import SVDpp  # type: ignore[import]

        return SVDpp(
            n_factors=int(hyperparams.get("n_factors", 20)),
            n_epochs=int(hyperparams.get("n_epochs", 20)),
            lr_all=float(hyperparams.get("lr_all", 0.007)),
            reg_all=float(hyperparams.get("reg_all", 0.02)),
        )
    if name_l == "surprise_knn":
        from surprise import KNNBasic  # type: ignore[import]

        return KNNBasic(
            k=int(hyperparams.get("k", 40)),
            min_k=int(hyperparams.get("min_k", 1)),
            sim_options={
                "name": hyperparams.get("sim_name", "cosine"),
                "user_based": bool(hyperparams.get("sim_user_based", True)),
            },
        )
    if name_l == "surprise_nmf":
        from surprise import NMF  # type: ignore[import]

        return NMF(
            n_factors=int(hyperparams.get("n_factors", 15)),
            n_epochs=int(hyperparams.get("n_epochs", 50)),
        )
    raise ValueError(f"unknown Surprise model: {name_l!r}")


def _fit_surprise(
    name: str,
    interactions: pd.DataFrame,
    hyperparams: dict[str, Any],
    seed: int,
) -> tuple[RecommenderWrapper, dict[str, float]]:
    """Random-row 80/20 split, fit Surprise, compute RMSE + MAE on holdout."""
    from surprise import Dataset, Reader  # type: ignore[import]
    from surprise.accuracy import mae, rmse  # type: ignore[import]
    from surprise.model_selection import train_test_split  # type: ignore[import]

    # Coerce ids to string — Surprise requires raw ids to be strings.
    inter = interactions.copy()
    inter["user_id"] = inter["user_id"].astype(str)
    inter["item_id"] = inter["item_id"].astype(str)
    inter["rating"] = inter["rating"].astype(float)

    min_r = float(inter["rating"].min())
    max_r = float(inter["rating"].max())
    # Guard against a constant-rating dataset (Surprise rejects it).
    if min_r == max_r:
        max_r = min_r + 1.0
    reader = Reader(rating_scale=(min_r, max_r))
    ds = Dataset.load_from_df(inter[["user_id", "item_id", "rating"]], reader)
    trainset, testset = train_test_split(ds, test_size=0.2, random_state=seed)

    algo = _build_surprise(name, hyperparams)
    algo.fit(trainset)
    preds = algo.test(testset)
    metrics = {
        "rmse": float(rmse(preds, verbose=False)),
        "mae": float(mae(preds, verbose=False)),
    }

    # Id maps for the wrapper — Surprise stores inner ids; we want the raw
    # ones the user sees in their dataset.
    idx_to_item = list({row[1] for row in testset} | set(inter["item_id"]))
    item_to_idx = {item: i for i, item in enumerate(idx_to_item)}
    user_ids = sorted(inter["user_id"].unique().tolist())
    user_to_idx = {u: i for i, u in enumerate(user_ids)}
    user_items: dict[int, set[int]] = {}
    for u, i in zip(inter["user_id"], inter["item_id"], strict=False):
        user_items.setdefault(user_to_idx[u], set()).add(item_to_idx[i])

    wrapper = RecommenderWrapper(
        backend="surprise",
        model=algo,
        user_to_idx=user_to_idx,
        item_to_idx=item_to_idx,
        idx_to_item=idx_to_item,
        user_items=user_items,
    )
    return wrapper, metrics


# -- implicit path ---------------------------------------------------------


def _fit_implicit(
    name: str,
    interactions: pd.DataFrame,
    hyperparams: dict[str, Any],
    seed: int,
) -> tuple[RecommenderWrapper, dict[str, float]]:
    """Fit ALS on a sparse confidence matrix, compute Precision@K + NDCG@K."""
    from implicit.als import AlternatingLeastSquares  # type: ignore[import]
    from scipy.sparse import csr_matrix  # type: ignore[import]

    _ = name  # currently only ALS routes here
    rng = np.random.default_rng(seed)

    inter = interactions.copy()
    user_ids = sorted(inter["user_id"].unique().tolist())
    item_ids = sorted(inter["item_id"].unique().tolist())
    user_to_idx = {u: i for i, u in enumerate(user_ids)}
    item_to_idx = {it: i for i, it in enumerate(item_ids)}
    idx_to_item = item_ids

    u_idx = inter["user_id"].map(user_to_idx).to_numpy()
    i_idx = inter["item_id"].map(item_to_idx).to_numpy()
    r = inter["rating"].astype(float).to_numpy()

    # Last-interaction-per-user holdout. Simple but avoids the random-row
    # leakage that plagues implicit splits (pair duplication across folds).
    inter_sorted = inter.reset_index(drop=True)
    holdout_idx = inter_sorted.groupby("user_id", sort=False).tail(1).index.to_numpy()
    train_mask = np.ones(len(inter_sorted), dtype=bool)
    train_mask[holdout_idx] = False

    alpha = float(hyperparams.get("alpha", 40.0))
    confidence_train = 1.0 + alpha * r[train_mask]
    train = csr_matrix(
        (confidence_train, (u_idx[train_mask], i_idx[train_mask])),
        shape=(len(user_ids), len(item_ids)),
    )

    model = AlternatingLeastSquares(
        factors=int(hyperparams.get("factors", 64)),
        regularization=float(hyperparams.get("regularization", 0.01)),
        iterations=int(hyperparams.get("iterations", 15)),
        random_state=seed,
    )
    model.fit(train, show_progress=False)

    # Evaluate top-K — Precision@K + Recall@K + NDCG@K across holdout users.
    k = int(hyperparams.get("eval_k", 10))
    test_confidence = 1.0 + alpha * r[~train_mask]
    test = csr_matrix(
        (test_confidence, (u_idx[~train_mask], i_idx[~train_mask])),
        shape=(len(user_ids), len(item_ids)),
    )

    precisions: list[float] = []
    recalls: list[float] = []
    ndcgs: list[float] = []
    for user in range(len(user_ids)):
        test_row = test[user]
        if test_row.nnz == 0:
            continue
        relevant = set(test_row.indices.tolist())
        ids, _scores = model.recommend(
            user,
            train[user],
            N=k,
            filter_already_liked_items=True,
        )
        recs = [int(x) for x in ids]
        hits = [1.0 if r_id in relevant else 0.0 for r_id in recs]
        precisions.append(float(sum(hits) / max(1, k)))
        recalls.append(float(sum(hits) / max(1, len(relevant))))
        # NDCG@K on binary relevance — log2(rank+2) discount.
        dcg = sum(h / np.log2(rank + 2) for rank, h in enumerate(hits))
        ideal = sum(1.0 / np.log2(rank + 2) for rank in range(min(k, len(relevant))))
        ndcgs.append(float(dcg / ideal) if ideal > 0 else 0.0)

    _ = rng  # reproducibility handle if we add noise-sampling later
    metrics = {
        f"precision_at_{k}": float(np.mean(precisions)) if precisions else 0.0,
        f"recall_at_{k}": float(np.mean(recalls)) if recalls else 0.0,
        f"ndcg_at_{k}": float(np.mean(ndcgs)) if ndcgs else 0.0,
    }

    user_items = {u: set(train[u].indices.tolist()) for u in range(len(user_ids))}
    wrapper = RecommenderWrapper(
        backend="implicit",
        model=model,
        user_to_idx=user_to_idx,
        item_to_idx=item_to_idx,
        idx_to_item=idx_to_item,
        user_items=user_items,
        confidence=train,
    )
    return wrapper, metrics


# -- public adapter entrypoint ---------------------------------------------


def fit_estimator(
    *,
    name: str,
    task3: str,
    task_class_map: dict[str, str],
    X_train: Any,
    y_train: Any,
    X_val: Any,
    y_val: Any,
    hyperparams: dict[str, Any],
) -> tuple[RecommenderWrapper, dict[str, float], dict[str, Any]]:
    """Fit a recommender from an interactions frame passed via hyperparams.

    The trainer hands the interactions frame in under the private
    ``_interactions`` hyperparameter. Feedback type (``_feedback_type``)
    selects the backend: ``explicit`` → Surprise, ``implicit`` → implicit.
    """
    _ = task3
    _ = task_class_map
    _ = X_train, X_val, y_train, y_val

    hp = dict(hyperparams or {})
    interactions: pd.DataFrame | None = hp.pop("_interactions", None)
    feedback_type: str = str(hp.pop("_feedback_type", "explicit"))
    seed: int = int(hp.pop("_split_seed", 42))
    if interactions is None or not isinstance(interactions, pd.DataFrame):
        raise ValueError(
            "recommender adapter expected _interactions frame in hyperparams"
        )

    name_l = name.strip().lower()
    if name_l.startswith("surprise_") or feedback_type == "explicit":
        wrapper, metrics = _fit_surprise(name, interactions, hp, seed)
    elif name_l == "implicit_als" or feedback_type == "implicit":
        wrapper, metrics = _fit_implicit(name, interactions, hp, seed)
    else:
        raise ValueError(f"unknown recommender model: {name_l!r}")

    effective = {str(k): v for k, v in hp.items()}
    return wrapper, metrics, effective


def prepare_hyperparams(name: str, hyperparams: dict[str, Any]) -> dict[str, Any]:
    _ = name
    return dict(hyperparams or {})


__all__ = ["RecommenderWrapper", "fit_estimator", "prepare_hyperparams"]
