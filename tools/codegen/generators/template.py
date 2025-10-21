from __future__ import annotations

"""Generic template-driven generator."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .base import CodeGenerator, GenerationRequest, GenerationResult


class TemplateGenerator(CodeGenerator):
    """Render a Jinja2 template with schema-derived context."""

    def __init__(self, extra_filters: dict[str, Any] | None = None) -> None:
        self.extra_filters = extra_filters or {}

    def _environment(self, template_dir: Path) -> Environment:
        env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )
        env.filters.update(self.extra_filters)
        return env

    def build_context(self, request: GenerationRequest) -> dict[str, Any]:
        """Override to build the template context."""

        return {
            "sources": request.sources,
            "metadata": request.metadata,
            "project_root": request.project_root,
        }

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if request.template is None:
            raise ValueError("Template path is required for template-based generation")
        template_path = request.template
        env = self._environment(template_path.parent)
        template = env.get_template(template_path.name)
        context = self.build_context(request)
        content = template.render(**context)
        if not content.endswith("\n"):
            content += "\n"
        return GenerationResult(content=content, diagnostics={"context_keys": list(context)})
