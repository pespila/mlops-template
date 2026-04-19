from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DeploymentCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_version_id: str
    name: str
    replicas: int = 1
    audit_payloads: bool = False


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    model_version_id: str
    name: str
    slug: str
    status: str
    container_id: str | None = None
    host_port: int | None = None
    endpoint_url: str | None = None
    internal_url: str | None = None
    replicas: int
    audit_payloads: bool
    last_health_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DeploymentList(BaseModel):
    items: list[DeploymentRead]
    total: int


class PredictRequest(BaseModel):
    inputs: dict[str, Any] | list[dict[str, Any]]


class PredictResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    prediction: Any
    model_version: str | None = None
    trace_id: str | None = None
