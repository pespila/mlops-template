from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# MLflow-side alias lifecycle after Batch 36. Promotion now writes
# ``@staging`` / ``@production`` to the MLflow registered model; the
# legacy four-state stage string is still exposed on the read schema
# for UI backward-compat but is derived from alias membership.
ModelStage = Literal["none", "staging", "production", "archived"]


class ModelVersionRead(BaseModel):
    """Projection of an MLflow ModelVersion for the UI.

    Fields come straight from the MLflow ``ModelVersion`` entity, with
    ``stage`` derived from the alias set (``@production`` → ``production``,
    ``@staging`` → ``staging``, else ``none``). The enriched fields
    (metrics, dataset, experiment) are resolved server-side by joining
    the MLflow run's platform.run_id tag back to the DB.
    """

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    # ID shape: ``{registered_model_name}:{version_number}`` — stable
    # across server restarts, unlike MLflow's own DB primary key.
    id: str
    registered_model_name: str
    registered_model_id: str  # alias for name, kept for frontend compat
    version: int
    stage: str
    aliases: list[str] = []
    run_id: str  # platform (DB) run id, read from the MLflow tag
    # mlflow_run_id kept off the read schema — used internally by the
    # worker / registry resolution but not surfaced to API consumers.
    model_kind: str
    storage_path: str | None = None
    input_schema_json: dict[str, Any] = {}
    output_schema_json: dict[str, Any] = {}
    serving_image_uri: str | None = None
    created_at: datetime
    updated_at: datetime
    # Enriched fields — populated by the router.
    metrics: dict[str, float] = {}
    dataset_id: str | None = None
    dataset_name: str | None = None
    experiment_id: str | None = None
    model_catalog_name: str | None = None


class ModelUpdate(BaseModel):
    # MLflow supports rename via rename_registered_model; renaming is
    # allowed but changes the immutable id, so every downstream consumer
    # (Deployment.registered_model_name, ModelPackage.registered_model_name)
    # would need a follow-up update — kept off for now.
    name: str | None = None
    description: str | None = None


class ModelVersionPromote(BaseModel):
    """Target stage for a ModelVersion promotion.

    Maps to MLflow aliases:
      * ``staging`` → sets ``@staging`` alias on the version.
      * ``production`` → sets ``@production`` (MLflow guarantees alias
        uniqueness per registered model, so the previous production
        version is automatically detached).
      * ``archived`` → removes ``@production`` if set.
      * ``none`` → removes any alias set by us.
    """

    stage: ModelStage


class RegisteredModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str  # equal to ``name`` for MLflow-backed rows
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class RegisteredModelDetail(RegisteredModelRead):
    versions: list[ModelVersionRead] = []


class RegisteredModelList(BaseModel):
    items: list[RegisteredModelRead]
    total: int
