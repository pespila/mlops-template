from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ModelCatalogEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    name: str
    framework: str
    description: str | None = None
    signature_json: dict[str, Any]
    origin: str
    image_uri: str | None = None


class ModelCatalogList(BaseModel):
    items: list[ModelCatalogEntryRead]
    total: int
