"""Dynamic Pydantic model builder from a JSON Schema fragment."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, create_model


_PY_TYPE: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _field_for(name: str, spec: dict[str, Any], required: bool) -> tuple[Any, Any]:
    """Resolve a JSON Schema property into a (type, FieldInfo) tuple."""
    schema_type = spec.get("type", "string")
    if isinstance(schema_type, list):
        schema_type = next((t for t in schema_type if t != "null"), "string")

    py_type: Any
    if "enum" in spec and isinstance(spec["enum"], list) and spec["enum"]:
        # Literal requires at least one value; keep string-only for simplicity.
        py_type = Literal[tuple(spec["enum"])]  # type: ignore[valid-type]
    else:
        py_type = _PY_TYPE.get(schema_type, Any)

    description = spec.get("description")
    if required:
        default: Any = ...
    else:
        default = spec.get("default", None)
        py_type = py_type | None if py_type is not Any else Any  # type: ignore[assignment]

    field = Field(default=default, description=description)
    return (py_type, field)


def pydantic_from_schema(schema: dict[str, Any], model_name: str = "ModelInput") -> type[BaseModel]:
    """Build a Pydantic model class from a JSON-Schema object-type fragment."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        # Permissive fallback — accept any dict.
        class _AnyModel(BaseModel):
            model_config = {"extra": "allow"}

        _AnyModel.__name__ = model_name
        return _AnyModel

    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    extras = schema.get("additionalProperties", False)

    fields: dict[str, tuple[Any, Any]] = {}
    for name, prop_spec in properties.items():
        if not isinstance(prop_spec, dict):
            prop_spec = {"type": "string"}
        fields[name] = _field_for(name, prop_spec, required=name in required)

    model = create_model(model_name, **fields)  # type: ignore[call-overload]
    model.model_config = {"extra": "allow" if extras else "ignore"}
    return model


__all__ = ["pydantic_from_schema"]
