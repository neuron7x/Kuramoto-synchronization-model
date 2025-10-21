from __future__ import annotations

"""Generator for Pandera validators derived from JSON schema."""

from typing import Any

from .template import TemplateGenerator
from .base import GenerationRequest


class ValidatorGenerator(TemplateGenerator):
    def build_context(self, request: GenerationRequest) -> dict[str, Any]:
        schema = next(iter(request.sources.values()))
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        fields: list[dict[str, Any]] = []
        for name, config in sorted(properties.items()):
            fields.append(
                {
                    "name": name,
                    "dtype": self._resolve_dtype(config.get("type")),
                    "nullable": name not in required,
                    "checks": self._build_checks(config),
                    "description": config.get("description", ""),
                }
            )
        return {
            "schema_name": request.metadata.get("schema_name", schema.get("title", "GeneratedFrameSchema")),
            "fields": fields,
            "metadata": request.metadata,
        }

    def _resolve_dtype(self, type_name: str | None) -> str:
        mapping = {
            "integer": "pa.Int64",
            "number": "pa.Float64",
            "boolean": "pa.Bool",
            "string": "pa.String",
            "object": "pa.Object",
        }
        return mapping.get(type_name or "", "pa.String")

    def _build_checks(self, config: dict[str, Any]) -> list[str]:
        checks: list[str] = []
        if "minimum" in config:
            checks.append(f"pa.Check.ge({config['minimum']})")
        if "maximum" in config:
            checks.append(f"pa.Check.le({config['maximum']})")
        if "pattern" in config:
            checks.append(f"pa.Check.str_matches(r'{config['pattern']}')")
        return checks
