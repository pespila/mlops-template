from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# Four-state stage lifecycle matching what the promote endpoint enforces:
#   none        — newly registered, never graduated.
#   staging     — auto-assigned by the trainer on train_run success.
#   production  — at most one per RegisteredModel (partial unique index).
#   archived    — previously-production version, retained for rollback.
ModelStage = Literal["none", "staging", "production", "archived"]


class ModelVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    registered_model_id: str
    run_id: str
    version: int
    stage: str
    model_kind: str
    storage_path: str | None = None
    input_schema_json: dict[str, Any]
    output_schema_json: dict[str, Any]
    serving_image_uri: str | None = None
    created_at: datetime
    updated_at: datetime
    # Enriched fields — populated by the router, not stored on the table.
    metrics: dict[str, float] = {}
    dataset_id: str | None = None
    dataset_name: str | None = None
    experiment_id: str | None = None
    model_catalog_name: str | None = None


class ModelUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ModelVersionPromote(BaseModel):
    """Target stage for a ModelVersion promotion.

    ``production`` at-most-one enforcement is done atomically server-side:
    any existing production version of the same RegisteredModel is moved
    to ``archived`` inside the same transaction as the promotion.
    """

    stage: ModelStage


class RegisteredModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class RegisteredModelDetail(RegisteredModelRead):
    versions: list[ModelVersionRead] = []


class RegisteredModelList(BaseModel):
    items: list[RegisteredModelRead]
    total: int
