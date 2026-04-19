from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatasetCreate(BaseModel):
    name: str


class FeatureSchemaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    dataset_id: str
    column_name: str
    inferred_type: str
    semantic_type: str | None = None
    missing_pct: float | None = None
    unique_count: int | None = None
    stats_json: dict[str, Any] | None = None

    # Frontend-facing aliases (semantic label, 0..1 null fraction)
    name: str = Field(default="", validation_alias="column_name")
    type: str = Field(default="text", validation_alias="semantic_type")
    null_fraction: float | None = Field(default=None, validation_alias="missing_pct")

    @classmethod
    def from_row(cls, row: Any) -> "FeatureSchemaRead":
        data = cls.model_validate(row)
        if data.missing_pct is not None and (data.null_fraction is None or data.null_fraction > 1.5):
            data.null_fraction = data.missing_pct / 100.0
        data.name = row.column_name
        data.type = row.semantic_type or _coarse_to_feature_type(row.inferred_type)
        return data


def _coarse_to_feature_type(dtype: str) -> str:
    d = dtype.lower()
    if "int" in d or "float" in d:
        return "numeric"
    if "bool" in d:
        return "boolean"
    if "datetime" in d or "date" in d or "time" in d:
        return "datetime"
    return "categorical"


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    user_id: str
    name: str
    source_filename: str | None = None
    row_count: int | None = None
    col_count: int | None = None
    # Frontend-facing alias
    column_count: int | None = Field(default=None, validation_alias="col_count")
    size_bytes: int | None = None
    storage_uri: str
    checksum: str | None = None
    status: str
    profile_uri: str | None = None
    created_at: datetime
    updated_at: datetime


class DatasetList(BaseModel):
    items: list[DatasetRead]
    total: int


class DatasetProfile(BaseModel):
    dataset_id: str
    summary: dict[str, Any] | None = None
    report_uri: str | None = None
