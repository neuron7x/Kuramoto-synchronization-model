# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Declarative DSL for composing strategy pipelines.

This module enables strategy research teams to describe complex evaluation
pipelines in a reproducible, self-documenting fashion.  A configuration is
expressed as YAML (or a rendered template), validated against strict pydantic
models, signed to guarantee integrity, and can be materialised into runtime
objects.  The implementation intentionally mirrors the ergonomics of the
existing CLI configuration helpers so the DSL integrates seamlessly with other
GeoSync tooling.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import random
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cached_property
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Literal

import numpy as np
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)

__all__ = [
    "ComponentParameters",
    "ParameterField",
    "StrategyComponentConfig",
    "StrategyDSLLoader",
    "StrategyMetadata",
    "StrategyPipeline",
    "StrategyPipelineDefinition",
    "StrategyPresetRegistry",
    "load_strategy_pipeline",
]


# ---------------------------------------------------------------------------
# Internal utilities


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        msg = f"Unrecognised boolean literal '{value}'"
        raise ValueError(msg)
    return bool(value)


def _coerce_scalar(value: Any, target: type) -> Any:
    if value is None:
        return None
    if target is bool:
        return _coerce_bool(value)
    if target is int:
        coerced = int(value)
        if isinstance(value, float) and not value.is_integer():
            msg = f"Cannot coerce non-integer float {value!r} to int"
            raise ValueError(msg)
        return coerced
    if target is float:
        return float(value)
    if target is str:
        return str(value)
    if target is Path:
        return Path(value)
    return value


_TYPE_REGISTRY: dict[str, type] = {
    "int": int,
    "float": float,
    "bool": bool,
    "str": str,
    "string": str,
    "path": Path,
    "dict": dict,
    "mapping": dict,
    "list": list,
    "sequence": list,
    "tuple": list,
    "json": dict,
}


def _coerce_value(value: Any, declared_type: str | None) -> Any:
    if declared_type is None or value is None:
        return value
    target_type = _TYPE_REGISTRY.get(declared_type.lower())
    if target_type is None:
        msg = f"Unsupported parameter type '{declared_type}'"
        raise ValueError(msg)
    if target_type in {dict, list}:
        if not isinstance(value, target_type):
            msg = f"Expected {target_type.__name__} for parameter, got {type(value).__name__}"
            raise ValueError(msg)
        return value
    return _coerce_scalar(value, target_type)


def _is_component_sequence(value: Any) -> bool:
    if not isinstance(value, Sequence):
        return False
    return all(isinstance(item, Mapping) and "id" in item for item in value)


def _merge_component_lists(
    existing: Sequence[Mapping[str, Any]], incoming: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    merged: dict[str, Mapping[str, Any]] = {str(item["id"]): dict(item) for item in existing}
    for item in incoming:
        identifier = str(item["id"])
        if identifier in merged:
            base_item = merged[identifier]
            if isinstance(base_item, MutableMapping):
                _deep_merge(base_item, item)
            else:
                merged[identifier] = dict(item)
        else:
            merged[identifier] = dict(item)
    return list(merged.values())


def _deep_merge(
    base: MutableMapping[str, Any], incoming: Mapping[str, Any]
) -> MutableMapping[str, Any]:
    """Recursively merge ``incoming`` into ``base`` (mutating ``base``)."""

    for key, value in incoming.items():
        if key not in base:
            base[key] = value
            continue
        current = base[key]
        if isinstance(current, MutableMapping) and isinstance(value, Mapping):
            _deep_merge(current, value)
        elif _is_component_sequence(current) and _is_component_sequence(value):
            base[key] = _merge_component_lists(current, value)
        else:
            base[key] = value
    return base


def _annotate_origin(payload: Any, origin: str) -> Any:
    if isinstance(payload, Mapping):
        annotated: dict[str, Any] = {}
        for key, value in payload.items():
            annotated[key] = _annotate_origin(value, origin)
        if {"value", "default"}.intersection(payload.keys()):
            annotated.setdefault("origin", origin)
        return annotated
    if isinstance(payload, list):
        return [_annotate_origin(item, origin) for item in payload]
    return payload


def _import_entrypoint(entrypoint: str) -> Any:
    if ":" not in entrypoint:
        msg = "Entrypoint must be in the form 'module:attribute'"
        raise ValueError(msg)
    module_name, attr_path = entrypoint.split(":", 1)
    module = import_module(module_name)
    target: Any = module
    for part in attr_path.split("."):
        if not hasattr(target, part):
            msg = f"Entrypoint attribute '{part}' not found on {target!r}"
            raise AttributeError(msg)
        target = getattr(target, part)
    return target


# ---------------------------------------------------------------------------
# Pydantic models representing the DSL schema


class ParameterField(BaseModel):
    """Represents a single parameter declaration."""

    value: Any | None = None
    default: Any | None = None
    type: str | None = None
    description: str | None = None
    choices: tuple[Any, ...] | None = None
    minimum: float | None = Field(default=None, alias="min")
    maximum: float | None = Field(default=None, alias="max")
    allow_none: bool = False
    origin: str = "inline"

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @model_validator(mode="after")
    def _validate_value(self) -> "ParameterField":
        resolved = self.resolved()
        if resolved is None and not self.allow_none:
            msg = "Parameter requires a value or default"
            raise ValueError(msg)
        if self.choices is not None and resolved is not None and resolved not in self.choices:
            msg = f"Value {resolved!r} not in allowed choices {self.choices!r}"
            raise ValueError(msg)
        if self.minimum is not None and resolved is not None:
            if float(resolved) < float(self.minimum):
                msg = f"Value {resolved!r} below minimum {self.minimum!r}"
                raise ValueError(msg)
        if self.maximum is not None and resolved is not None:
            if float(resolved) > float(self.maximum):
                msg = f"Value {resolved!r} above maximum {self.maximum!r}"
                raise ValueError(msg)
        if self.type is not None:
            coerced = _coerce_value(resolved, self.type)
            if self.value is not None:
                self.value = coerced
            elif coerced is not None:
                self.default = coerced
        return self

    def resolved(self) -> Any:
        return self.value if self.value is not None else self.default

    def render_for_docs(self) -> str:
        resolved = self.resolved()
        if isinstance(resolved, Path):
            return str(resolved)
        if isinstance(resolved, (dict, list, tuple)):
            return json.dumps(resolved, sort_keys=True, ensure_ascii=False)
        return json.dumps(resolved, ensure_ascii=False)


class ComponentParameters(BaseModel):
    """Grouping of required and optional parameters for a component."""

    required: Dict[str, ParameterField] = Field(default_factory=dict)
    optional: Dict[str, ParameterField] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _auto_allow_optional_none(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        optional = value.get("optional")
        if isinstance(optional, Mapping):
            for field in optional.values():
                if isinstance(field, MutableMapping) and "allow_none" not in field:
                    field["allow_none"] = True
        return value

    def require(self) -> dict[str, Any]:
        return {
            name: field.resolved()
            for name, field in self.required.items()
            if field.resolved() is not None
        }

    def optional_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name, field in self.optional.items():
            resolved = field.resolved()
            if resolved is not None:
                values[name] = resolved
        return values

    def combined(self) -> dict[str, Any]:
        values = self.optional_values()
        values.update(self.require())
        return values

    def describe(self) -> dict[str, dict[str, ParameterField]]:
        return {"required": self.required, "optional": self.optional}


class StrategyComponentConfig(BaseModel):
    """Definition of a single pipeline component."""

    id: str
    kind: Literal[
        "datasource",
        "feature",
        "model",
        "strategy",
        "risk",
        "execution",
        "report",
        "postprocess",
    ]
    entrypoint: str
    parameters: ComponentParameters = Field(default_factory=ComponentParameters)
    description: str | None = None
    depends_on: tuple[str, ...] = ()
    enabled: bool = True
    preset: str | None = None
    template: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not value:
            raise ValueError("Component id cannot be empty")
        return value

    @cached_property
    def callable(self) -> Callable[..., Any]:
        return _import_entrypoint(self.entrypoint)

    def to_runtime(self) -> "StrategyComponentRuntime":
        return StrategyComponentRuntime(
            component_id=self.id,
            kind=self.kind,
            entrypoint=self.entrypoint,
            callable=self.callable,
            parameters=self.parameters,
            description=self.description,
            depends_on=self.depends_on,
            enabled=self.enabled,
            preset=self.preset,
            template=self.template,
        )


class StrategyMetadata(BaseModel):
    """General metadata describing the strategy pipeline."""

    name: str
    owner: str | None = None
    description: str | None = None
    version: str = "1.0"
    tags: tuple[str, ...] = ()
    preset: str | None = None
    template: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("tags")
    @classmethod
    def _normalise_tags(cls, value: Sequence[str]) -> tuple[str, ...]:
        deduped = sorted({tag.strip() for tag in value if tag and tag.strip()})
        return tuple(deduped)


class RuntimeSettings(BaseModel):
    """Settings ensuring deterministic execution."""

    seed: PositiveInt
    environment: str = "backtest"
    deterministic: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(extra="forbid")

    def apply(self) -> None:
        os.environ["PYTHONHASHSEED"] = str(self.seed)
        random.seed(self.seed)
        np.random.seed(self.seed)


class StrategyPipelineDefinition(BaseModel):
    """Validated representation of a strategy pipeline configuration."""

    version: str = "1.0"
    metadata: StrategyMetadata
    runtime: RuntimeSettings
    pipeline: tuple[StrategyComponentConfig, ...]
    artifacts: tuple[str, ...] = ()
    signature: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _assign_signature(self) -> "StrategyPipelineDefinition":
        self.signature = self.compute_signature()
        return self

    def compute_signature(self) -> str:
        payload = self.model_dump(exclude={"signature"}, mode="json")
        if isinstance(payload, dict):
            runtime = payload.get("runtime")
            if isinstance(runtime, dict):
                runtime.pop("created_at", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def instantiate(self) -> "StrategyPipeline":
        components = tuple(
            component.to_runtime() for component in self.pipeline if component.enabled
        )
        return StrategyPipeline(
            metadata=self.metadata,
            runtime=self.runtime,
            components=components,
            signature=self.signature or "",
        )

    def generate_documentation(self) -> str:
        lines = [f"# Strategy Pipeline: {self.metadata.name}", ""]
        if self.metadata.description:
            lines.append(self.metadata.description)
            lines.append("")
        lines.extend(
            [
                f"**Version:** {self.metadata.version}",
                f"**Owner:** {self.metadata.owner or 'n/a'}",
                f"**Tags:** {', '.join(self.metadata.tags) if self.metadata.tags else 'n/a'}",
                f"**Preset:** {self.metadata.preset or 'n/a'}",
                f"**Template:** {self.metadata.template or 'n/a'}",
                f"**Signature:** `{self.signature}`",
                "",
                "## Runtime",
                f"- Seed: `{self.runtime.seed}`",
                f"- Environment: `{self.runtime.environment}`",
                f"- Deterministic: `{self.runtime.deterministic}`",
                f"- Created: `{self.runtime.created_at.isoformat()}`",
                "",
                "## Components",
            ]
        )
        for component in self.pipeline:
            lines.extend(
                [
                    f"### {component.id} ({component.kind})",
                    f"- Entry point: `{component.entrypoint}`",
                    f"- Enabled: `{component.enabled}`",
                    f"- Depends on: {', '.join(component.depends_on) if component.depends_on else 'none'}",
                    f"- Preset: {component.preset or 'n/a'}",
                    f"- Template: {component.template or 'n/a'}",
                ]
            )
            if component.description:
                lines.append(component.description)
            lines.append("")
            lines.append("#### Required Parameters")
            if component.parameters.required:
                lines.append("| Name | Value | Type | Origin | Description |")
                lines.append("| --- | --- | --- | --- | --- |")
                for name, field in component.parameters.required.items():
                    lines.append(
                        "| {name} | {value} | {type} | {origin} | {desc} |".format(
                            name=name,
                            value=field.render_for_docs(),
                            type=field.type or "auto",
                            origin=field.origin,
                            desc=field.description or "",
                        )
                    )
            else:
                lines.append("(none)")
            lines.append("")
            lines.append("#### Optional Parameters")
            if component.parameters.optional:
                lines.append("| Name | Value | Type | Origin | Description |")
                lines.append("| --- | --- | --- | --- | --- |")
                for name, field in component.parameters.optional.items():
                    lines.append(
                        "| {name} | {value} | {type} | {origin} | {desc} |".format(
                            name=name,
                            value=field.render_for_docs(),
                            type=field.type or "auto",
                            origin=field.origin,
                            desc=field.description or "",
                        )
                    )
            else:
                lines.append("(none)")
            lines.append("")
        return "\n".join(lines).strip() + "\n"


@dataclass(slots=True)
class StrategyComponentRuntime:
    component_id: str
    kind: str
    entrypoint: str
    callable: Callable[..., Any]
    parameters: ComponentParameters
    description: str | None
    depends_on: tuple[str, ...]
    enabled: bool
    preset: str | None
    template: str | None

    def combined_parameters(self) -> dict[str, Any]:
        return self.parameters.combined()

    def create(self) -> Any:
        params = self.combined_parameters()
        target = self.callable
        if inspect.isclass(target):
            return target(**params)
        if callable(target):
            return target(**params)
        return target


@dataclass(slots=True)
class StrategyPipeline:
    metadata: StrategyMetadata
    runtime: RuntimeSettings
    components: tuple[StrategyComponentRuntime, ...]
    signature: str

    def materialise(self) -> dict[str, Any]:
        self.runtime.apply()
        return {component.component_id: component.create() for component in self.components}


# ---------------------------------------------------------------------------
# Presets and loader


class StrategyPresetRegistry:
    """Load reusable fragments that can seed DSL configurations."""

    def __init__(self, search_paths: Iterable[Path] | None = None) -> None:
        self._paths = tuple(search_paths or ())
        self._presets: dict[str, Mapping[str, Any]] = {}
        for root in self._paths:
            self.register_path(root)

    def register_path(self, root: Path) -> None:
        if not root.exists():
            return
        for file in root.glob("*.y*ml"):
            data = yaml.safe_load(file.read_text(encoding="utf-8"))
            if not isinstance(data, Mapping):
                msg = f"Preset file {file} must contain a mapping"
                raise ValueError(msg)
            name = str(data.get("name") or file.stem)
            annotated = _annotate_origin(data, f"preset:{name}")
            if isinstance(annotated, MutableMapping):
                annotated.pop("name", None)
            self._presets[name] = annotated

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._presets))

    def resolve(self, name: str) -> Mapping[str, Any]:
        try:
            payload = self._presets[name]
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise KeyError(f"Unknown strategy preset '{name}'") from exc
        return copy.deepcopy(payload)


class StrategyDSLLoader:
    """Parse, template, and validate strategy pipeline configurations."""

    def __init__(
        self,
        *,
        preset_dirs: Sequence[Path] | None = None,
        template_dirs: Sequence[Path] | None = None,
    ) -> None:
        self._presets = StrategyPresetRegistry(preset_dirs)
        self._template_env: Environment | None = None
        if template_dirs:
            self._template_env = Environment(
                loader=FileSystemLoader([str(path) for path in template_dirs]),
                autoescape=select_autoescape(enabled_extensions=(".yaml", ".yml")),
                undefined=StrictUndefined,
                trim_blocks=True,
                lstrip_blocks=True,
            )

    def load(
        self, path: Path, *, context: Mapping[str, Any] | None = None
    ) -> StrategyPipelineDefinition:
        text = self._render(path, context=context)
        data = yaml.safe_load(text)
        if not isinstance(data, Mapping):
            raise ValueError("Strategy configuration must be a mapping")
        processed = self._apply_includes(data, base_path=path.parent)
        return StrategyPipelineDefinition.model_validate(processed)

    def load_from_dict(self, data: Mapping[str, Any]) -> StrategyPipelineDefinition:
        processed = self._apply_includes(data, base_path=None)
        return StrategyPipelineDefinition.model_validate(processed)

    def _render(self, path: Path, *, context: Mapping[str, Any] | None) -> str:
        if path.suffix in {".j2", ".jinja", ".jinja2"}:
            env = self._template_env
            if env is None:
                env = Environment(
                    loader=FileSystemLoader([str(path.parent)]),
                    autoescape=select_autoescape(enabled_extensions=(".yaml", ".yml")),
                    undefined=StrictUndefined,
                    trim_blocks=True,
                    lstrip_blocks=True,
                )
            template = env.get_template(path.name)
            render_context = {
                "env": dict(os.environ),
                **(context or {}),
                "base_path": str(path.parent),
            }
            return template.render(**render_context)
        return path.read_text(encoding="utf-8")

    def _apply_includes(
        self, data: Mapping[str, Any], *, base_path: Path | None
    ) -> Mapping[str, Any]:
        extends = data.get("extends")
        merged: dict[str, Any] = {}
        inherited_presets: list[str] = []
        if extends:
            references: Sequence[Any]
            if isinstance(extends, (str, Mapping)):
                references = [extends]
            elif isinstance(extends, Sequence):
                references = extends
            else:
                msg = "extends must be a string, mapping, or sequence"
                raise ValueError(msg)
            for ref in references:
                base, preset_name = self._resolve_reference(ref, base_path)
                if preset_name:
                    inherited_presets.append(preset_name)
                _deep_merge(merged, base)
        own = {k: v for k, v in data.items() if k != "extends"}
        _deep_merge(merged, own)
        if inherited_presets:
            metadata = merged.setdefault("metadata", {})
            if isinstance(metadata, MutableMapping) and not metadata.get("preset"):
                metadata["preset"] = inherited_presets[-1]
        return merged

    def _resolve_reference(
        self, ref: Any, base_path: Path | None
    ) -> tuple[Mapping[str, Any], str | None]:
        if isinstance(ref, str):
            return self._presets.resolve(ref), ref
        if isinstance(ref, Mapping):
            if "preset" in ref:
                name = str(ref["preset"])
                return self._presets.resolve(name), name
            if "path" in ref:
                include_path = Path(ref["path"])
                if not include_path.is_absolute() and base_path is not None:
                    include_path = base_path / include_path
                text = self._render(include_path, context=None)
                included = yaml.safe_load(text)
                if not isinstance(included, Mapping):
                    msg = f"Included file {include_path} must contain a mapping"
                    raise ValueError(msg)
                return included, None
        msg = f"Unsupported extends reference: {ref!r}"
        raise ValueError(msg)


def load_strategy_pipeline(
    path: Path | str,
    *,
    preset_dirs: Sequence[Path] | None = None,
    template_dirs: Sequence[Path] | None = None,
    context: Mapping[str, Any] | None = None,
) -> StrategyPipelineDefinition:
    loader = StrategyDSLLoader(preset_dirs=preset_dirs, template_dirs=template_dirs)
    return loader.load(Path(path), context=context)
