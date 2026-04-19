from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatasetCreate(BaseModel):
    name: str


class FeatureSchemaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    column_name: str
    inferred_type: str
    semantic_type: str | None = None
    missing_pct: float | None = None
    unique_count: int | None = None
    stats_json: dict[str, Any] | None = None


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
