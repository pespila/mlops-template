from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TaskKind = Literal["regression", "binary_classification", "multiclass_classification"]


class HpoSearchRangeInt(BaseModel):
    type: Literal["int"]
    low: int
    high: int
    step: int | None = None
    log: bool = False


class HpoSearchRangeFloat(BaseModel):
    type: Literal["float"]
    low: float
    high: float
    log: bool = False


class HpoSearchCategorical(BaseModel):
    type: Literal["categorical"]
    choices: list[str | bool | int | float]


HpoSearchEntry = Annotated[
    HpoSearchRangeInt | HpoSearchRangeFloat | HpoSearchCategorical,
    Field(discriminator="type"),
]


class HpoConfig(BaseModel):
    enabled: bool = False
    n_trials: int = Field(default=30, ge=2, le=500)
    timeout_sec: int = Field(default=1800, ge=60, le=7200)
    metric: str | None = None
    direction: Literal["maximize", "minimize"] | None = None
    search_space: dict[str, HpoSearchEntry] = {}


class RunCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    experiment_id: str
    dataset_id: str
    model_catalog_id: str
    transform_config_id: str | None = None
    transform_config: dict[str, Any] | None = None
    hyperparams: dict[str, Any] = {}
    resource_limits: dict[str, Any] = {}
    # User-chosen task override. When null the trainer falls back to inferring
    # from the target column's dtype/cardinality.
    task: TaskKind | None = None
    # Optional HPO configuration. When null or ``enabled=false`` the run is a
    # single point fit with ``hyperparams`` as-is (legacy behaviour).
    hpo: HpoConfig | None = None


class RunUpdate(BaseModel):
    display_name: str | None = None


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    experiment_id: str
    dataset_id: str
    transform_config_id: str
    model_catalog_id: str
    display_name: str | None = None
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
    """Frontend-facing artifact row.

    The DB column is still named `uri` for historical reasons but it stores a
    relative path under `/var/platform-data`. `download_url` is computed.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    run_id: str
    kind: str
    name: str
    uri: str
    size_bytes: int | None = None
    content_type: str | None = None
    download_url: str = Field(default="")

    @classmethod
    def from_row(cls, row: Any) -> "ArtifactRead":
        data = cls.model_validate(row)
        data.download_url = f"/api/artifacts/{data.id}/download"
        return data
