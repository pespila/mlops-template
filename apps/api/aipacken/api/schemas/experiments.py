from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExperimentCreate(BaseModel):
    name: str
    description: str | None = None


class ExperimentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class ExperimentList(BaseModel):
    items: list[ExperimentRead]
    total: int
