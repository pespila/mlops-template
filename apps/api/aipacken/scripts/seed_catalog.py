from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aipacken.db.models import ModelCatalogEntry

logger = structlog.get_logger(__name__)


# Tasks (supervised):
#   "regression"                 -> numeric target
#   "binary_classification"      -> 2-class target
#   "multiclass_classification"  -> >2-class target
#
# New task families (added alongside supervised): "forecasting", "recommender",
# "clustering". Each uses its own fit_protocol + serving_mode (see below).
#
# `kind` is a coarse DB-level bucket for indexing/informational use; the actual
# per-task estimator class lives in signature_json.task_class_map.
#
# signature_json now also carries:
#   fit_protocol:   "sklearn" | "sktime" | "surprise" | "implicit" | "autogluon"
#                   — adapter dispatcher reads this to route fit calls.
#   serving_mode:   "predict" | "assign" | "forecast" | "recommend_topk"
#                   | "recommend_score"
#                   — build_package chooses the predict.py template from this.
#   required_columns: {roles: [...], feedback_type?: "explicit"|"implicit"}
#                   — per-family role spec used by the wizard's Step 5.


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
    fit_protocol: str = "sklearn",
    serving_mode: str = "predict",
    required_columns: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if kind is None:
        if supported_tasks == ["regression"]:
            kind = "regression"
        elif "regression" not in supported_tasks:
            kind = "classification"
        else:
            kind = "supervised"
    if required_columns is None:
        required_columns = {"roles": ["target"]}
    signature: dict[str, Any] = {
        "hyperparams": hyperparams,
        "supported_tasks": supported_tasks,
        "task_class_map": task_class_map,
        "fit_protocol": fit_protocol,
        "serving_mode": serving_mode,
        "required_columns": required_columns,
    }
    out: dict[str, Any] = {
        "kind": kind,
        "name": name,
        "framework": framework,
        "description": description,
        "signature_json": signature,
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
                "type": "float",
                "default": 0.1,
                "min": 0.001,
                "max": 1.0,
                "log": True,
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
                "type": "float",
                "default": 0.1,
                "min": 0.001,
                "max": 1.0,
                "log": True,
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
                "type": "float",
                "default": 1.0,
                "min": 0.001,
                "max": 10.0,
                "log": True,
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
                "type": "float",
                "default": 0.1,
                "min": 0.001,
                "max": 1.0,
                "log": True,
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
                "type": "float",
                "default": 0.1,
                "min": 0.001,
                "max": 1.0,
                "log": True,
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
        fit_protocol="autogluon",
    ),
    # --- Clustering (unsupervised) ----------------------------------------
    # Roles for clustering: feature columns only. Metrics are internal
    # (silhouette / Calinski-Harabasz / Davies-Bouldin). KMeans / MBKM / GMM
    # are inductive (`.predict` on new points); DBSCAN + Agglomerative are
    # transductive and served via 1-NN assignment against the training set.
    _entry(
        name="sklearn_kmeans",
        framework="scikit-learn",
        description="KMeans — centroid-based clustering, inductive (predicts new points).",
        hyperparams={
            "n_clusters": {"type": "int", "default": 8, "min": 2, "max": 100},
            "init": {"type": "enum", "default": "k-means++", "choices": ["k-means++", "random"]},
            "n_init": {"type": "int", "default": 10, "min": 1, "max": 50},
            "max_iter": {"type": "int", "default": 300, "min": 10, "max": 5000},
        },
        supported_tasks=["clustering"],
        task_class_map={"clustering": "sklearn.cluster.KMeans"},
        kind="clustering",
        fit_protocol="sklearn_cluster",
        serving_mode="predict",
        required_columns={"roles": ["features"]},
    ),
    _entry(
        name="sklearn_minibatch_kmeans",
        framework="scikit-learn",
        description="MiniBatchKMeans — KMeans variant that scales to large datasets.",
        hyperparams={
            "n_clusters": {"type": "int", "default": 8, "min": 2, "max": 100},
            "batch_size": {"type": "int", "default": 1024, "min": 64, "max": 100000},
            "max_iter": {"type": "int", "default": 100, "min": 10, "max": 5000},
            "n_init": {"type": "int", "default": 3, "min": 1, "max": 50},
        },
        supported_tasks=["clustering"],
        task_class_map={"clustering": "sklearn.cluster.MiniBatchKMeans"},
        kind="clustering",
        fit_protocol="sklearn_cluster",
        serving_mode="predict",
        required_columns={"roles": ["features"]},
    ),
    _entry(
        name="sklearn_gaussian_mixture",
        framework="scikit-learn",
        description="Gaussian Mixture Model — soft clustering, inductive (.predict).",
        hyperparams={
            "n_components": {"type": "int", "default": 8, "min": 2, "max": 100},
            "covariance_type": {
                "type": "enum",
                "default": "full",
                "choices": ["full", "tied", "diag", "spherical"],
            },
            "max_iter": {"type": "int", "default": 100, "min": 10, "max": 5000},
            "n_init": {"type": "int", "default": 1, "min": 1, "max": 20},
        },
        supported_tasks=["clustering"],
        task_class_map={"clustering": "sklearn.mixture.GaussianMixture"},
        kind="clustering",
        fit_protocol="sklearn_cluster",
        serving_mode="predict",
        required_columns={"roles": ["features"]},
    ),
    _entry(
        name="sklearn_dbscan",
        framework="scikit-learn",
        description=(
            "DBSCAN — density-based clustering. Transductive: new points are "
            "assigned via 1-NN on the training set at serve time."
        ),
        hyperparams={
            "eps": {"type": "float", "default": 0.5, "min": 0.01, "max": 10.0, "log": True},
            "min_samples": {"type": "int", "default": 5, "min": 1, "max": 200},
            "metric": {
                "type": "enum",
                "default": "euclidean",
                "choices": ["euclidean", "manhattan", "cosine"],
            },
        },
        supported_tasks=["clustering"],
        task_class_map={"clustering": "sklearn.cluster.DBSCAN"},
        kind="clustering",
        fit_protocol="sklearn_cluster",
        serving_mode="assign",
        required_columns={"roles": ["features"]},
    ),
    _entry(
        name="sklearn_agglomerative",
        framework="scikit-learn",
        description=(
            "Agglomerative / hierarchical clustering (Ward linkage). "
            "Transductive: serves via 1-NN on training points."
        ),
        hyperparams={
            "n_clusters": {"type": "int", "default": 8, "min": 2, "max": 100},
            "linkage": {
                "type": "enum",
                "default": "ward",
                "choices": ["ward", "complete", "average", "single"],
            },
            "metric": {
                "type": "enum",
                "default": "euclidean",
                "choices": ["euclidean", "manhattan", "cosine", "l1", "l2"],
            },
        },
        supported_tasks=["clustering"],
        task_class_map={"clustering": "sklearn.cluster.AgglomerativeClustering"},
        kind="clustering",
        fit_protocol="sklearn_cluster",
        serving_mode="assign",
        required_columns={"roles": ["features"]},
    ),
    # --- Forecasting (sktime) ---------------------------------------------
    # All five forecasters share the sktime BaseForecaster contract so the
    # trainer adapter can treat them uniformly. Tuple hyperparams (ARIMA
    # order / SARIMAX seasonal_order) are flattened to independent ints.
    _entry(
        name="sktime_naive",
        framework="sktime",
        description="Naive baseline — last value / mean / drift. Cheap reference.",
        hyperparams={
            "strategy": {
                "type": "enum",
                "default": "last",
                "choices": ["last", "mean", "drift"],
            },
            "sp": {"type": "int", "default": 1, "min": 1, "max": 365},
        },
        supported_tasks=["forecasting"],
        task_class_map={"forecasting": "sktime.forecasting.naive.NaiveForecaster"},
        kind="forecasting",
        fit_protocol="sktime",
        serving_mode="forecast",
        required_columns={"roles": ["time", "target"]},
    ),
    _entry(
        name="sktime_theta",
        framework="sktime",
        description="Theta method — simple but strong Box-Jenkins baseline.",
        hyperparams={
            "sp": {"type": "int", "default": 1, "min": 1, "max": 365},
            "deseasonalize": {"type": "bool", "default": True},
        },
        supported_tasks=["forecasting"],
        task_class_map={"forecasting": "sktime.forecasting.theta.ThetaForecaster"},
        kind="forecasting",
        fit_protocol="sktime",
        serving_mode="forecast",
        required_columns={"roles": ["time", "target"]},
    ),
    _entry(
        name="sktime_ets",
        framework="sktime",
        description="Exponential smoothing (Holt-Winters) with trend + seasonality.",
        hyperparams={
            "trend": {
                "type": "enum",
                "default": "add",
                "choices": ["add", "mul", "none"],
            },
            "seasonal": {
                "type": "enum",
                "default": "none",
                "choices": ["add", "mul", "none"],
            },
            "sp": {"type": "int", "default": 1, "min": 1, "max": 365},
            "damped_trend": {"type": "bool", "default": False},
        },
        supported_tasks=["forecasting"],
        task_class_map={"forecasting": "sktime.forecasting.exp_smoothing.ExponentialSmoothing"},
        kind="forecasting",
        fit_protocol="sktime",
        serving_mode="forecast",
        required_columns={"roles": ["time", "target"]},
    ),
    _entry(
        name="sktime_arima",
        framework="sktime",
        description="ARIMA(p, d, q) — classical Box-Jenkins autoregressive model.",
        hyperparams={
            "p": {"type": "int", "default": 1, "min": 0, "max": 5},
            "d": {"type": "int", "default": 0, "min": 0, "max": 2},
            "q": {"type": "int", "default": 0, "min": 0, "max": 5},
        },
        supported_tasks=["forecasting"],
        task_class_map={"forecasting": "sktime.forecasting.arima.ARIMA"},
        kind="forecasting",
        fit_protocol="sktime",
        serving_mode="forecast",
        required_columns={"roles": ["time", "target"]},
    ),
    _entry(
        name="sktime_sarimax",
        framework="sktime",
        description=(
            "SARIMAX — seasonal ARIMA with optional exogenous regressors. "
            "Hyperparams flatten order=(p,d,q) and seasonal_order=(P,D,Q,s)."
        ),
        hyperparams={
            "p": {"type": "int", "default": 1, "min": 0, "max": 5},
            "d": {"type": "int", "default": 0, "min": 0, "max": 2},
            "q": {"type": "int", "default": 0, "min": 0, "max": 5},
            "P": {"type": "int", "default": 0, "min": 0, "max": 3},
            "D": {"type": "int", "default": 0, "min": 0, "max": 2},
            "Q": {"type": "int", "default": 0, "min": 0, "max": 3},
            "s": {"type": "int", "default": 0, "min": 0, "max": 365},
        },
        supported_tasks=["forecasting"],
        task_class_map={"forecasting": "sktime.forecasting.arima.ARIMA"},
        kind="forecasting",
        fit_protocol="sktime",
        serving_mode="forecast",
        required_columns={"roles": ["time", "target"]},
    ),
    # --- Recommender Engines ----------------------------------------------
    # Four Surprise models for explicit feedback (RMSE / MAE) + implicit ALS
    # for implicit feedback (Precision@K / Recall@K / NDCG@K). The adapter
    # dispatches internally on ``feedback_type``; serving templates on
    # ``recommend_topk`` (implicit) vs ``recommend_score`` (explicit).
    _entry(
        name="surprise_svd",
        framework="scikit-surprise",
        description="SVD — matrix factorization for explicit feedback (Simon Funk style).",
        hyperparams={
            "n_factors": {"type": "int", "default": 100, "min": 5, "max": 500},
            "n_epochs": {"type": "int", "default": 20, "min": 1, "max": 200},
            "lr_all": {
                "type": "float",
                "default": 0.005,
                "min": 0.0001,
                "max": 0.1,
                "log": True,
            },
            "reg_all": {
                "type": "float",
                "default": 0.02,
                "min": 0.0001,
                "max": 1.0,
                "log": True,
            },
        },
        supported_tasks=["recommender"],
        task_class_map={"recommender": "surprise.SVD"},
        kind="recommender",
        fit_protocol="surprise",
        serving_mode="recommend_score",
        required_columns={
            "roles": ["user_id", "item_id", "rating"],
            "feedback_type": "explicit",
        },
    ),
    _entry(
        name="surprise_svdpp",
        framework="scikit-surprise",
        description="SVD++ — extends SVD with implicit user bias terms.",
        hyperparams={
            "n_factors": {"type": "int", "default": 20, "min": 5, "max": 200},
            "n_epochs": {"type": "int", "default": 20, "min": 1, "max": 200},
            "lr_all": {
                "type": "float",
                "default": 0.007,
                "min": 0.0001,
                "max": 0.1,
                "log": True,
            },
            "reg_all": {
                "type": "float",
                "default": 0.02,
                "min": 0.0001,
                "max": 1.0,
                "log": True,
            },
        },
        supported_tasks=["recommender"],
        task_class_map={"recommender": "surprise.SVDpp"},
        kind="recommender",
        fit_protocol="surprise",
        serving_mode="recommend_score",
        required_columns={
            "roles": ["user_id", "item_id", "rating"],
            "feedback_type": "explicit",
        },
    ),
    _entry(
        name="surprise_knn",
        framework="scikit-surprise",
        description="KNNBasic — user- or item-based collaborative filtering.",
        hyperparams={
            "k": {"type": "int", "default": 40, "min": 1, "max": 200},
            "min_k": {"type": "int", "default": 1, "min": 1, "max": 100},
            "sim_name": {
                "type": "enum",
                "default": "cosine",
                "choices": ["cosine", "pearson", "msd", "pearson_baseline"],
            },
            "sim_user_based": {"type": "bool", "default": True},
        },
        supported_tasks=["recommender"],
        task_class_map={"recommender": "surprise.KNNBasic"},
        kind="recommender",
        fit_protocol="surprise",
        serving_mode="recommend_score",
        required_columns={
            "roles": ["user_id", "item_id", "rating"],
            "feedback_type": "explicit",
        },
    ),
    _entry(
        name="surprise_nmf",
        framework="scikit-surprise",
        description="NMF — non-negative matrix factorization for explicit ratings.",
        hyperparams={
            "n_factors": {"type": "int", "default": 15, "min": 5, "max": 200},
            "n_epochs": {"type": "int", "default": 50, "min": 1, "max": 500},
        },
        supported_tasks=["recommender"],
        task_class_map={"recommender": "surprise.NMF"},
        kind="recommender",
        fit_protocol="surprise",
        serving_mode="recommend_score",
        required_columns={
            "roles": ["user_id", "item_id", "rating"],
            "feedback_type": "explicit",
        },
    ),
    _entry(
        name="implicit_als",
        framework="implicit",
        description=(
            "Alternating Least Squares for implicit feedback — "
            "confidence-weighted matrix factorization."
        ),
        hyperparams={
            "factors": {"type": "int", "default": 64, "min": 8, "max": 512},
            "regularization": {
                "type": "float",
                "default": 0.01,
                "min": 0.0001,
                "max": 1.0,
                "log": True,
            },
            "iterations": {"type": "int", "default": 15, "min": 1, "max": 200},
            "alpha": {
                "type": "float",
                "default": 40.0,
                "min": 1.0,
                "max": 1000.0,
                "log": True,
            },
        },
        supported_tasks=["recommender"],
        task_class_map={"recommender": "implicit.als.AlternatingLeastSquares"},
        kind="recommender",
        fit_protocol="implicit",
        serving_mode="recommend_topk",
        required_columns={
            "roles": ["user_id", "item_id", "rating"],
            "feedback_type": "implicit",
        },
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
