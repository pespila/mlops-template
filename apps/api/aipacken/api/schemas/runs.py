from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RunCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    experiment_id: str
    dataset_id: str
    model_catalog_id: str
    transform_config_id: str | None = None
    transform_config: dict[str, Any] | None = None
    hyperparams: dict[str, Any] = {}
    resource_limits: dict[str, Any] = {}


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    experiment_id: str
    dataset_id: str
    transform_config_id: str
    model_catalog_id: str
    mlflow_run_id: str | None = None
    image_uri: str | None = None
    container_id: str | None = None
    status: str
    hyperparams_json: dict[str, Any]
    resource_limits_json: dict[str, Any]
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RunList(BaseModel):
    items: list[RunRead]
    total: int


class MetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    name: str
    value: float
    step: int | None = None
    phase: str | None = None


class ArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    kind: str
    uri: str
    size_bytes: int | None = None
    content_type: str | None = None
