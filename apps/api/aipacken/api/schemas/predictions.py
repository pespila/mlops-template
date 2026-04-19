from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PredictionIngest(BaseModel):
    deployment_id: str
    received_at: datetime
    latency_ms: float | None = None
    mode: str = "online"
    input_ref: str | None = None
    output_ref: str | None = None
    status_code: int
    trace_id: str | None = None
    input_preview_json: dict[str, Any] | None = None
    output_preview_json: dict[str, Any] | None = None


class PredictionBulkIngest(BaseModel):
    items: list[PredictionIngest]


class PredictionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deployment_id: str
    received_at: datetime
    latency_ms: float | None = None
    mode: str
    status_code: int
    trace_id: str | None = None
    input_preview_json: dict[str, Any] | None = None
    output_preview_json: dict[str, Any] | None = None


class PredictionList(BaseModel):
    items: list[PredictionRead]
    total: int
    page: int
    page_size: int
