from __future__ import annotations

"""Configuration models for the TradePulse code generation runtime."""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SmokeTestConfig(BaseModel):
    """Declarative configuration for smoke tests executed post-generation."""

    name: str
    type: Literal["contains", "import", "exec"]
    options: dict[str, Any] = Field(default_factory=dict)


class TaskConfig(BaseModel):
    """Declarative configuration of a single code generation task."""

    name: str
    generator: str
    sources: list[Path]
    template: Path | None = None
    output: Path
    publish_artifact: bool = True
    update_mode: Literal["if_changed", "always", "manual"] = "if_changed"
    smoke_tests: list[SmokeTestConfig] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    migrations: bool = False
    diff_strict: bool = True

    @model_validator(mode="after")
    def _make_paths_absolute(self) -> "TaskConfig":
        project_root = self.metadata.get("project_root")
        if project_root is None:
            return self
        root_path = Path(project_root)
        self.sources = [root_path / src if not src.is_absolute() else src for src in self.sources]
        if self.template is not None and not self.template.is_absolute():
            self.template = root_path / self.template
        if not self.output.is_absolute():
            self.output = root_path / self.output
        return self


class RuntimeConfig(BaseModel):
    """Runtime parameters shared across tasks during execution."""

    cache_dir: Path
    artifacts_dir: Path
    version_file: Path = Path("VERSION")
    lock_file: Path | None = None

    @model_validator(mode="after")
    def _absolute_paths(self) -> "RuntimeConfig":
        self.cache_dir = self.cache_dir.expanduser().resolve()
        self.artifacts_dir = self.artifacts_dir.expanduser().resolve()
        if self.lock_file is not None:
            self.lock_file = self.lock_file.expanduser().resolve()
        self.version_file = self.version_file.expanduser().resolve()
        return self


class CodegenConfig(BaseModel):
    """Top-level configuration for the code generation engine."""

    tasks: list[TaskConfig]
    runtime: RuntimeConfig

    @model_validator(mode="after")
    def _inject_root_path(self) -> "CodegenConfig":
        root = Path.cwd().resolve()
        for task in self.tasks:
            task.metadata.setdefault("project_root", str(root))
        return self


def load_config(path: Path | str) -> CodegenConfig:
    """Load configuration from a YAML or JSON document."""

    path = Path(path).resolve()
    content = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        import yaml

        data: dict[str, Any] = yaml.safe_load(content) or {}
    else:
        import json

        data = json.loads(content)
    return CodegenConfig.model_validate(data)
