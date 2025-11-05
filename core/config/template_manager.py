"""Utility helpers for loading and rendering CLI configuration templates."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Type, TypeVar

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ConfigTemplateManager:
    """Load YAML templates and parse them into strongly typed configs."""

    def __init__(self, template_dir: Path) -> None:
        if not template_dir.exists():
            raise FileNotFoundError(
                f"Template directory '{template_dir}' does not exist"
            )
        self.template_dir = template_dir
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(enabled_extensions=(".yaml", ".yml")),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(
        self,
        template_name: str,
        destination: Path,
        context: Mapping[str, Any] | None = None,
    ) -> Path:
        template = self._env.get_template(f"{template_name}.yaml.j2")
        rendered = template.render(context or {})
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
        return destination

    def load_raw(self, path: Path) -> Dict[str, Any]:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(
                "Configuration files must define a mapping at the top level"
            )
        return data

    def load_config(self, path: Path, model: Type[T]) -> T:
        raw = self.load_raw(path)
        context = {"base_path": str(path.parent)}
        return model.model_validate(raw, context=context)
