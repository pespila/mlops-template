from __future__ import annotations

from functools import lru_cache
from typing import Any

import structlog

from aipacken.config import get_settings

logger = structlog.get_logger(__name__)


@lru_cache
def get_mlflow_client() -> Any:
    from mlflow.tracking import MlflowClient  # mlflow-skinny offers this lazily

    settings = get_settings()
    return MlflowClient(tracking_uri=settings.mlflow_tracking_uri)


def ensure_experiment(name: str) -> str:
    client = get_mlflow_client()
    exp = client.get_experiment_by_name(name)
    if exp is not None:
        return exp.experiment_id
    return client.create_experiment(name)


def create_run(experiment_id: str, run_name: str | None = None) -> str:
    run = get_mlflow_client().create_run(
        experiment_id=experiment_id, run_name=run_name
    )
    return run.info.run_id


def register_model(name: str, source: str, run_id: str | None = None) -> Any:
    client = get_mlflow_client()
    try:
        client.create_registered_model(name)
    except Exception:  # noqa: BLE001 — create is idempotent in practice
        pass
    return client.create_model_version(name=name, source=source, run_id=run_id)


def get_model_version(name: str, version: str) -> Any:
    return get_mlflow_client().get_model_version(name=name, version=version)
