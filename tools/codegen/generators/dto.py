from __future__ import annotations

"""Generator that builds Pydantic DTOs from JSON schema definitions."""

from typing import Any

from .template import TemplateGenerator
from .base import GenerationRequest


class DtoGenerator(TemplateGenerator):
    def build_context(self, request: GenerationRequest) -> dict[str, Any]:
        schema = next(iter(request.sources.values()))
        properties = schema.get("properties", {})
        fields: list[dict[str, Any]] = []
        required = set(schema.get("required", []))
        for name, config in sorted(properties.items()):
            default_value = config.get("default")
            fields.append(
                {
                    "name": name,
                    "type": self._resolve_type(config),
                    "required": name in required,
                    "description": config.get("description", ""),
                    "default_repr": repr(default_value) if default_value is not None else "None",
                }
            )
        return {
            "model_name": schema.get("title", request.metadata.get("default_model_name", "GeneratedModel")),
            "fields": fields,
            "metadata": request.metadata,
        }

    def _resolve_type(self, config: dict[str, Any]) -> str:
        type_name = config.get("type", "Any")
        if type_name == "array":
            items = config.get("items", {})
            return f"list[{self._resolve_type(items)}]"
        if type_name == "object":
            return "dict[str, Any]"
        mapping = {"integer": "int", "number": "float", "boolean": "bool", "string": "str"}
        return mapping.get(type_name, "Any")
