from __future__ import annotations

"""Generator for HTTP API clients based on OpenAPI-like specifications."""

from typing import Any

from .template import TemplateGenerator
from .base import GenerationRequest


class ApiClientGenerator(TemplateGenerator):
    """Build a typed httpx client from a simplified OpenAPI schema."""

    def build_context(self, request: GenerationRequest) -> dict[str, Any]:
        raw_schema = next(iter(request.sources.values()))
        info = raw_schema.get("info", {})
        servers = raw_schema.get("servers", [{"url": info.get("x-default-server", "") }])
        base_url = servers[0]["url"] if servers else ""
        paths = raw_schema.get("paths", {})
        operations: list[dict[str, Any]] = []
        for path, methods in sorted(paths.items()):
            for method, config in sorted(methods.items()):
                operation = {
                    "name": config.get("operationId", f"{method}_{path}".replace("/", "_")),
                    "method": method.upper(),
                    "path": path,
                    "summary": config.get("summary", ""),
                    "response_model": config.get("responses", {}).get("200", {}).get("$ref"),
                    "params": self._extract_parameters(config),
                    "request_body": self._extract_request_body(config),
                }
                operations.append(operation)
        return {
            "client_name": info.get("title", "GeneratedClient").replace(" ", ""),
            "base_url": base_url,
            "operations": operations,
            "metadata": request.metadata,
        }

    def _extract_parameters(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        parameters = config.get("parameters", [])
        normalized: list[dict[str, Any]] = []
        for param in parameters:
            schema = param.get("schema", {})
            normalized.append(
                {
                    "name": param.get("name"),
                    "in": param.get("in"),
                    "required": param.get("required", False),
                    "python_type": self._resolve_type(schema.get("type")),
                    "description": param.get("description", ""),
                }
            )
        return normalized

    def _extract_request_body(self, config: dict[str, Any]) -> dict[str, Any] | None:
        request_body = config.get("requestBody")
        if not request_body:
            return None
        content = request_body.get("content", {})
        for media_type, details in sorted(content.items()):
            schema = details.get("schema", {})
            return {
                "media_type": media_type,
                "schema_ref": schema.get("$ref"),
            }
        return None

    def _resolve_type(self, schema_type: str | None) -> str:
        mapping = {"integer": "int", "number": "float", "boolean": "bool", "string": "str"}
        return mapping.get(schema_type or "", "Any")
