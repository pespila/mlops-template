from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field


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

    # Frontend-facing aliases.
    # `family` groups + filters the catalog — use `name` (e.g. `sklearn_logistic`,
    # `autogluon`), not `kind` (task type like `classification`).
    family: str = Field(default="", validation_alias="name")
    hyperparam_schema: dict[str, Any] = Field(
        default_factory=dict, validation_alias="signature_json"
    )
    tags: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def supported_tasks(self) -> list[str]:
        raw = (self.signature_json or {}).get("supported_tasks") or []
        return [str(t) for t in raw if isinstance(t, str)]


class ModelCatalogList(BaseModel):
    items: list[ModelCatalogEntryRead]
    total: int
