from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelCatalogEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    kind: str
    name: str
    framework: str
    description: str | None = None
    signature_json: dict[str, Any]
    origin: str
    image_uri: str | None = None

    # Frontend-facing aliases
    family: str = Field(default="", validation_alias="kind")
    hyperparam_schema: dict[str, Any] = Field(
        default_factory=dict, validation_alias="signature_json"
    )
    tags: list[str] = Field(default_factory=list)


class ModelCatalogList(BaseModel):
    items: list[ModelCatalogEntryRead]
    total: int
