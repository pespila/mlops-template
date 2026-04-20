from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.db.models import ModelCatalogEntry

logger = structlog.get_logger(__name__)


# Tasks:
#   "regression"                 -> numeric target
#   "binary_classification"      -> 2-class target
#   "multiclass_classification"  -> >2-class target
# `kind` is a coarse DB-level bucket for indexing/informational use; the actual
# per-task estimator class lives in signature_json.task_class_map and adapter
# dispatch routes on `name`.


def _entry(
    *,
    name: str,
    framework: str,
    description: str,
    hyperparams: dict[str, dict[str, Any]],
    supported_tasks: list[str],
    task_class_map: dict[str, str],
    kind: str | None = None,
    image_uri: str | None = None,
) -> dict[str, Any]:
    if kind is None:
        if supported_tasks == ["regression"]:
            kind = "regression"
        elif "regression" not in supported_tasks:
            kind = "classification"
        else:
            kind = "supervised"
    out: dict[str, Any] = {
        "kind": kind,
        "name": name,
        "framework": framework,
        "description": description,
        "signature_json": {
            "hyperparams": hyperparams,
            "supported_tasks": supported_tasks,
            "task_class_map": task_class_map,
        },
    }
    if image_uri is not None:
        out["image_uri"] = image_uri
    return out


ALL_TASKS = ["regression", "binary_classification", "multiclass_classification"]


CATALOG: list[dict[str, Any]] = [
    # --- scikit-learn: linear family ---------------------------------------
    _entry(
        name="sklearn_linear",
        framework="scikit-learn",
        description="Linear Regression (OLS) — baseline regression.",
        hyperparams={
            "fit_intercept": {"type": "bool", "default": True},
        },
        supported_tasks=["regression"],
        task_class_map={"regression": "sklearn.linear_model.LinearRegression"},
    ),
    _entry(
        name="sklearn_ridge",
        framework="scikit-learn",
        description="Ridge regression/classifier with L2 regularization.",
        hyperparams={
            "alpha": {"type": "float", "default": 1.0, "min": 0.0001, "max": 1000.0, "log": True},
            "fit_intercept": {"type": "bool", "default": True},
        },
        supported_tasks=ALL_TASKS,
        task_class_map={
            "regression": "sklearn.linear_model.Ridge",
            "binary_classification": "sklearn.linear_model.RidgeClassifier",
            "multiclass_classification": "sklearn.linear_model.RidgeClassifier",
        },
    ),
    _entry(
        name="sklearn_lasso",
        framework="scikit-learn",
        description="Lasso regression with L1 regularization.",
        hyperparams={
            "alpha": {"type": "float", "default": 1.0, "min": 0.0001, "max": 1000.0, "log": True},
            "max_iter": {"type": "int", "default": 1000, "min": 100, "max": 100000},
        },
        supported_tasks=["regression"],
        task_class_map={"regression": "sklearn.linear_model.Lasso"},
    ),
    _entry(
        name="sklearn_elasticnet",
        framework="scikit-learn",
        description="ElasticNet — combined L1/L2 regression.",
        hyperparams={
            "alpha": {"type": "float", "default": 1.0, "min": 0.0001, "max": 1000.0, "log": True},
            "l1_ratio": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.0},
            "max_iter": {"type": "int", "default": 1000, "min": 100, "max": 100000},
        },
        supported_tasks=["regression"],
        task_class_map={"regression": "sklearn.linear_model.ElasticNet"},
    ),
    _entry(
        name="sklearn_logistic",
        framework="scikit-learn",
        description="Logistic Regression (scikit-learn) — linear baseline for classification.",
        hyperparams={
            "C": {"type": "float", "default": 1.0, "min": 0.0001, "max": 1000.0, "log": True},
            "max_iter": {"type": "int", "default": 200, "min": 50, "max": 10000},
            "penalty": {"type": "enum", "default": "l2", "choices": ["l2", "none"]},
        },
        supported_tasks=["binary_classification", "multiclass_classification"],
        task_class_map={
            "binary_classification": "sklearn.linear_model.LogisticRegression",
            "multiclass_classification": "sklearn.linear_model.LogisticRegression",
        },
    ),
    # --- scikit-learn: svm -------------------------------------------------
    _entry(
        name="sklearn_svm",
        framework="scikit-learn",
        description="Support Vector Machine — RBF kernel by default.",
        hyperparams={
            "C": {"type": "float", "default": 1.0, "min": 0.001, "max": 1000.0, "log": True},
            "kernel": {
                "type": "enum",
                "default": "rbf",
                "choices": ["linear", "poly", "rbf", "sigmoid"],
            },
            "gamma": {"type": "enum", "default": "scale", "choices": ["scale", "auto"]},
        },
        supported_tasks=ALL_TASKS,
        task_class_map={
            "regression": "sklearn.svm.SVR",
            "binary_classification": "sklearn.svm.SVC",
            "multiclass_classification": "sklearn.svm.SVC",
        },
    ),
    # --- scikit-learn: neighbors ------------------------------------------
    _entry(
        name="sklearn_knn",
        framework="scikit-learn",
        description="K-Nearest Neighbors — regressor / classifier.",
        hyperparams={
            "n_neighbors": {"type": "int", "default": 5, "min": 1, "max": 200},
            "weights": {"type": "enum", "default": "uniform", "choices": ["uniform", "distance"]},
            "p": {"type": "int", "default": 2, "min": 1, "max": 4},
        },
        supported_tasks=ALL_TASKS,
        task_class_map={
            "regression": "sklearn.neighbors.KNeighborsRegressor",
            "binary_classification": "sklearn.neighbors.KNeighborsClassifier",
            "multiclass_classification": "sklearn.neighbors.KNeighborsClassifier",
        },
    ),
    # --- scikit-learn: trees & forests ------------------------------------
    _entry(
        name="sklearn_decision_tree",
        framework="scikit-learn",
        description="Decision Tree — single-tree baseline.",
        hyperparams={
            "max_depth": {"type": "int", "default": 10, "min": 1, "max": 64},
            "min_samples_split": {"type": "int", "default": 2, "min": 2, "max": 64},
            "min_samples_leaf": {"type": "int", "default": 1, "min": 1, "max": 64},
        },
        supported_tasks=ALL_TASKS,
        task_class_map={
            "regression": "sklearn.tree.DecisionTreeRegressor",
            "binary_classification": "sklearn.tree.DecisionTreeClassifier",
            "multiclass_classification": "sklearn.tree.DecisionTreeClassifier",
        },
    ),
    _entry(
        name="sklearn_random_forest",
        framework="scikit-learn",
        description="Random Forest — bagged decision trees.",
        hyperparams={
            "n_estimators": {"type": "int", "default": 100, "min": 10, "max": 2000},
            "max_depth": {"type": "int", "default": 10, "min": 1, "max": 64},
            "min_samples_split": {"type": "int", "default": 2, "min": 2, "max": 64},
            "min_samples_leaf": {"type": "int", "default": 1, "min": 1, "max": 64},
            "max_features": {
                "type": "enum",
                "default": "sqrt",
                "choices": ["sqrt", "log2"],
            },
        },
        supported_tasks=ALL_TASKS,
        task_class_map={
            "regression": "sklearn.ensemble.RandomForestRegressor",
            "binary_classification": "sklearn.ensemble.RandomForestClassifier",
            "multiclass_classification": "sklearn.ensemble.RandomForestClassifier",
        },
    ),
    _entry(
        name="sklearn_extra_trees",
        framework="scikit-learn",
        description="Extra Trees — extremely randomized forest.",
        hyperparams={
            "n_estimators": {"type": "int", "default": 100, "min": 10, "max": 2000},
            "max_depth": {"type": "int", "default": 10, "min": 1, "max": 64},
            "min_samples_split": {"type": "int", "default": 2, "min": 2, "max": 64},
            "min_samples_leaf": {"type": "int", "default": 1, "min": 1, "max": 64},
            "max_features": {
                "type": "enum",
                "default": "sqrt",
                "choices": ["sqrt", "log2"],
            },
        },
        supported_tasks=ALL_TASKS,
        task_class_map={
            "regression": "sklearn.ensemble.ExtraTreesRegressor",
            "binary_classification": "sklearn.ensemble.ExtraTreesClassifier",
            "multiclass_classification": "sklearn.ensemble.ExtraTreesClassifier",
        },
    ),
    # --- scikit-learn: boosting -------------------------------------------
    _entry(
        name="sklearn_gradient_boosting",
        framework="scikit-learn",
        description="Gradient Boosting (scikit-learn).",
        hyperparams={
            "n_estimators": {"type": "int", "default": 200, "min": 10, "max": 5000},
            "learning_rate": {
                "type": "float", "default": 0.1, "min": 0.001, "max": 1.0, "log": True,
            },
            "max_depth": {"type": "int", "default": 3, "min": 1, "max": 16},
            "subsample": {"type": "float", "default": 1.0, "min": 0.1, "max": 1.0},
        },
        supported_tasks=ALL_TASKS,
        task_class_map={
            "regression": "sklearn.ensemble.GradientBoostingRegressor",
            "binary_classification": "sklearn.ensemble.GradientBoostingClassifier",
            "multiclass_classification": "sklearn.ensemble.GradientBoostingClassifier",
        },
    ),
    _entry(
        name="sklearn_hist_gbm",
        framework="scikit-learn",
        description="HistGradientBoosting — histogram-based, fast on large data.",
        hyperparams={
            "learning_rate": {
                "type": "float", "default": 0.1, "min": 0.001, "max": 1.0, "log": True,
            },
            "max_iter": {"type": "int", "default": 100, "min": 10, "max": 5000},
            "max_depth": {"type": "int", "default": 8, "min": 1, "max": 64},
            "l2_regularization": {"type": "float", "default": 0.0, "min": 0.0, "max": 10.0},
        },
        supported_tasks=ALL_TASKS,
        task_class_map={
            "regression": "sklearn.ensemble.HistGradientBoostingRegressor",
            "binary_classification": "sklearn.ensemble.HistGradientBoostingClassifier",
            "multiclass_classification": "sklearn.ensemble.HistGradientBoostingClassifier",
        },
    ),
    _entry(
        name="sklearn_ada_boost",
        framework="scikit-learn",
        description="AdaBoost — adaptive boosting of weak learners.",
        hyperparams={
            "n_estimators": {"type": "int", "default": 50, "min": 10, "max": 2000},
            "learning_rate": {
                "type": "float", "default": 1.0, "min": 0.001, "max": 10.0, "log": True,
            },
        },
        supported_tasks=ALL_TASKS,
        task_class_map={
            "regression": "sklearn.ensemble.AdaBoostRegressor",
            "binary_classification": "sklearn.ensemble.AdaBoostClassifier",
            "multiclass_classification": "sklearn.ensemble.AdaBoostClassifier",
        },
    ),
    # --- scikit-learn: neural net & naive bayes ---------------------------
    _entry(
        name="sklearn_mlp",
        framework="scikit-learn",
        description="Multi-layer Perceptron (feed-forward neural network).",
        hyperparams={
            "hidden_layer_sizes": {
                "type": "enum",
                "default": "(100,)",
                "choices": ["(64,)", "(100,)", "(128,)", "(64,32)", "(128,64)", "(128,64,32)"],
            },
            "activation": {
                "type": "enum",
                "default": "relu",
                "choices": ["relu", "tanh", "logistic"],
            },
            "alpha": {"type": "float", "default": 0.0001, "min": 1e-6, "max": 1.0, "log": True},
            "learning_rate_init": {
                "type": "float",
                "default": 0.001,
                "min": 1e-5,
                "max": 1.0,
                "log": True,
            },
            "max_iter": {"type": "int", "default": 200, "min": 50, "max": 5000},
        },
        supported_tasks=ALL_TASKS,
        task_class_map={
            "regression": "sklearn.neural_network.MLPRegressor",
            "binary_classification": "sklearn.neural_network.MLPClassifier",
            "multiclass_classification": "sklearn.neural_network.MLPClassifier",
        },
    ),
    _entry(
        name="sklearn_naive_bayes",
        framework="scikit-learn",
        description="Gaussian Naive Bayes — probabilistic classifier.",
        hyperparams={
            "var_smoothing": {
                "type": "float",
                "default": 1e-9,
                "min": 1e-12,
                "max": 1e-3,
                "log": True,
            },
        },
        supported_tasks=["binary_classification", "multiclass_classification"],
        task_class_map={
            "binary_classification": "sklearn.naive_bayes.GaussianNB",
            "multiclass_classification": "sklearn.naive_bayes.GaussianNB",
        },
    ),
    # --- XGBoost -----------------------------------------------------------
    _entry(
        name="xgboost",
        framework="xgboost",
        description="XGBoost — gradient-boosted decision trees.",
        hyperparams={
            "n_estimators": {"type": "int", "default": 200, "min": 10, "max": 5000},
            "max_depth": {"type": "int", "default": 6, "min": 1, "max": 16},
            "learning_rate": {
                "type": "float", "default": 0.1, "min": 0.001, "max": 1.0, "log": True,
            },
            "subsample": {"type": "float", "default": 1.0, "min": 0.1, "max": 1.0},
            "colsample_bytree": {"type": "float", "default": 1.0, "min": 0.1, "max": 1.0},
            "reg_alpha": {"type": "float", "default": 0.0, "min": 0.0, "max": 10.0},
            "reg_lambda": {"type": "float", "default": 1.0, "min": 0.0, "max": 10.0},
        },
        supported_tasks=ALL_TASKS,
        task_class_map={
            "regression": "xgboost.XGBRegressor",
            "binary_classification": "xgboost.XGBClassifier",
            "multiclass_classification": "xgboost.XGBClassifier",
        },
    ),
    # --- LightGBM ----------------------------------------------------------
    _entry(
        name="lightgbm",
        framework="lightgbm",
        description="LightGBM — fast histogram-based gradient boosting.",
        hyperparams={
            "n_estimators": {"type": "int", "default": 200, "min": 10, "max": 5000},
            "num_leaves": {"type": "int", "default": 31, "min": 2, "max": 4096},
            "learning_rate": {
                "type": "float", "default": 0.1, "min": 0.001, "max": 1.0, "log": True,
            },
            "max_depth": {"type": "int", "default": -1, "min": -1, "max": 64},
            "min_child_samples": {"type": "int", "default": 20, "min": 1, "max": 1000},
            "subsample": {"type": "float", "default": 1.0, "min": 0.1, "max": 1.0},
            "colsample_bytree": {"type": "float", "default": 1.0, "min": 0.1, "max": 1.0},
        },
        supported_tasks=ALL_TASKS,
        task_class_map={
            "regression": "lightgbm.LGBMRegressor",
            "binary_classification": "lightgbm.LGBMClassifier",
            "multiclass_classification": "lightgbm.LGBMClassifier",
        },
    ),
    # --- AutoGluon ---------------------------------------------------------
    _entry(
        name="autogluon",
        framework="autogluon",
        description="AutoGluon TabularPredictor — zero-config AutoML.",
        # AutoGluon pins older xgboost/lightgbm than our base trainer; ship it
        # in a dedicated image so the two versions don't collide.
        image_uri="platform/trainer-base-autogluon:latest",
        hyperparams={
            "time_limit": {"type": "int", "default": 600, "min": 60, "max": 36000},
            "presets": {
                "type": "enum",
                "default": "medium_quality",
                "choices": [
                    "medium_quality",
                    "good_quality",
                    "high_quality",
                    "best_quality",
                ],
            },
        },
        supported_tasks=ALL_TASKS,
        task_class_map={
            "regression": "autogluon.tabular.TabularPredictor",
            "binary_classification": "autogluon.tabular.TabularPredictor",
            "multiclass_classification": "autogluon.tabular.TabularPredictor",
        },
        kind="classification",
    ),
]


async def seed_catalog(db: AsyncSession) -> int:
    """Idempotently create or update catalog entries.

    Rows are matched by ``name``. Existing rows have their metadata (kind,
    framework, description, signature_json, image_uri) refreshed so adding new
    fields (``supported_tasks`` / ``task_class_map``) to already-seeded
    databases doesn't require a manual migration.
    """
    rows = (await db.execute(select(ModelCatalogEntry))).scalars().all()
    existing_by_name = {r.name: r for r in rows}
    created = 0
    updated = 0
    for entry in CATALOG:
        row = existing_by_name.get(entry["name"])
        if row is None:
            db.add(ModelCatalogEntry(**entry))
            created += 1
            continue
        changed = False
        for field in ("kind", "framework", "description", "signature_json", "image_uri"):
            new_val = entry.get(field)
            if getattr(row, field) != new_val:
                setattr(row, field, new_val)
                changed = True
        if changed:
            updated += 1
    if created or updated:
        await db.commit()
        logger.info("seed.catalog.upserted", created=created, updated=updated)
    return created + updated
