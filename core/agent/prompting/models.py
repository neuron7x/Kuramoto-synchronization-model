"""Domain models supporting the prompt management subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .exceptions import PromptGuardrailViolation

__all__ = [
    "ParameterSpec",
    "PromptGuardrail",
    "PromptTemplate",
    "ContextFragment",
    "PromptContext",
    "PromptContextWindow",
    "PromptRenderResult",
    "PromptExecutionRecord",
    "PromptOutcome",
]


@dataclass(slots=True, frozen=True)
class ParameterSpec:
    """Description of a single template parameter."""

    name: str
    required: bool = True
    allow_empty: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("parameter name must be a non-empty string")
        object.__setattr__(self, "name", self.name.strip())


class PromptGuardrail:
    """Abstract guardrail invoked prior to rendering a template."""

    description: str

    def __init__(self, description: str | None = None) -> None:
        self.description = description or self.__class__.__name__

    def validate(self, parameters: Mapping[str, str], context: "PromptContext") -> None:
        """Validate *parameters* and *context*.

        Sub-classes should raise :class:`PromptGuardrailViolation` when validation
        fails. The base implementation enforces no additional behaviour and is
        provided so simple guardrails can override only the pieces they need.
        """

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"{self.__class__.__name__}(description={self.description!r})"


@dataclass(slots=True, frozen=True)
class PromptTemplate:
    """Immutable representation of a prompt template variant."""

    family: str
    version: str
    content: str
    variant: str = "control"
    description: str = ""
    parameters: tuple[ParameterSpec, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    guardrails: tuple[PromptGuardrail, ...] = ()

    def __post_init__(self) -> None:
        family = self.family.strip()
        variant = self.variant.strip()
        version = self.version.strip()
        if not family:
            raise ValueError("family must be a non-empty string")
        if not version:
            raise ValueError("version must be a non-empty string")
        if not variant:
            raise ValueError("variant must be a non-empty string")
        if not self.content:
            raise ValueError("content must be a non-empty string")
        object.__setattr__(self, "family", family)
        object.__setattr__(self, "variant", variant)
        object.__setattr__(self, "version", version)

        metadata = (
            MappingProxyType(dict(self.metadata))
            if self.metadata
            else MappingProxyType({})
        )
        object.__setattr__(self, "metadata", metadata)

        parameter_names = {spec.name for spec in self.parameters}
        if len(parameter_names) != len(self.parameters):
            raise ValueError("parameter names must be unique")

    @property
    def parameter_index(self) -> Mapping[str, ParameterSpec]:
        """Return a mapping of parameter names to their specifications."""

        return {spec.name: spec for spec in self.parameters}

    @property
    def required_parameters(self) -> set[str]:
        """Return the set of required parameter names."""

        return {spec.name for spec in self.parameters if spec.required}

    def validate_parameters(self, provided: Mapping[str, str]) -> None:
        """Ensure provided parameters satisfy template requirements."""

        missing = self.required_parameters - provided.keys()
        if missing:
            raise PromptGuardrailViolation(
                f"Missing required parameter(s): {', '.join(sorted(missing))}"
            )

        allowed = set(spec.name for spec in self.parameters)
        extra = provided.keys() - allowed
        if extra:
            raise PromptGuardrailViolation(
                f"Unexpected parameter(s): {', '.join(sorted(extra))}"
            )

        for spec in self.parameters:
            value = provided.get(spec.name)
            if value is None:
                continue
            if not spec.allow_empty and not value.strip():
                raise PromptGuardrailViolation(
                    f"Parameter '{spec.name}' must not be empty"
                )

    def apply_guardrails(
        self, parameters: Mapping[str, str], context: "PromptContext"
    ) -> None:
        """Execute guardrails registered on the template."""

        for guardrail in self.guardrails:
            guardrail.validate(parameters, context)


@dataclass(slots=True)
class ContextFragment:
    """Individual fragment contributing additional context to a prompt."""

    label: str
    content: str
    priority: int = 0
    allow_truncate: bool = True
    min_chars: int = 0

    def __post_init__(self) -> None:
        if not self.label or not self.label.strip():
            raise ValueError("fragment label must be non-empty")
        if self.min_chars < 0:
            raise ValueError("min_chars must be non-negative")
        self.label = self.label.strip()

    def truncated(self, max_chars: int) -> "ContextFragment":
        """Return a truncated copy of the fragment."""

        if max_chars < self.min_chars:
            max_chars = self.min_chars
        truncated_content = self.content[: max(0, max_chars)].rstrip()
        return ContextFragment(
            label=self.label,
            content=truncated_content,
            priority=self.priority,
            allow_truncate=self.allow_truncate,
            min_chars=self.min_chars,
        )


@dataclass(slots=True)
class PromptContext:
    """Execution context accompanying a template render."""

    fragments: tuple[ContextFragment, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        fragments = tuple(self.fragments)
        object.__setattr__(self, "fragments", fragments)
        metadata = (
            MappingProxyType(dict(self.metadata))
            if self.metadata
            else MappingProxyType({})
        )
        object.__setattr__(self, "metadata", metadata)

    def sorted_fragments(self) -> tuple[ContextFragment, ...]:
        """Return fragments sorted by priority (descending)."""

        return tuple(
            sorted(self.fragments, key=lambda fragment: fragment.priority, reverse=True)
        )


@dataclass(slots=True, frozen=True)
class PromptContextWindow:
    """Constraints describing the available prompt window."""

    max_chars: int
    soft_chars: int | None = None
    separator: str = "\n\n"

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be positive")
        if self.soft_chars is not None and (
            self.soft_chars <= 0 or self.soft_chars > self.max_chars
        ):
            raise ValueError("soft_chars must be positive and <= max_chars")
        if not self.separator:
            raise ValueError("separator must be non-empty")


@dataclass(slots=True, frozen=True)
class PromptExecutionRecord:
    """Immutable audit entry capturing the details of a render."""

    record_id: str
    template_family: str
    template_version: str
    variant: str
    prompt_checksum: str
    parameters: Mapping[str, str]
    included_fragments: tuple[ContextFragment, ...]
    truncated_fragments: tuple[ContextFragment, ...]
    timestamp: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @staticmethod
    def create(
        *,
        record_id: str,
        template: PromptTemplate,
        prompt_text: str,
        parameters: Mapping[str, str],
        included: Sequence[ContextFragment],
        truncated: Sequence[ContextFragment],
        metadata: Mapping[str, Any] | None = None,
    ) -> "PromptExecutionRecord":
        digest = sha256(prompt_text.encode("utf-8")).hexdigest()
        timestamp = datetime.now(timezone.utc)
        return PromptExecutionRecord(
            record_id=record_id,
            template_family=template.family,
            template_version=template.version,
            variant=template.variant,
            prompt_checksum=digest,
            parameters=MappingProxyType(dict(parameters)),
            included_fragments=tuple(included),
            truncated_fragments=tuple(truncated),
            timestamp=timestamp,
            metadata=MappingProxyType(dict(metadata or {})),
        )


@dataclass(slots=True, frozen=True)
class PromptOutcome:
    """Outcome supplied after a prompt interaction has completed."""

    success: bool
    effect: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        metadata = (
            MappingProxyType(dict(self.metadata))
            if self.metadata
            else MappingProxyType({})
        )
        object.__setattr__(self, "metadata", metadata)


@dataclass(slots=True)
class PromptRenderResult:
    """Value object returned by :class:`PromptManager` renders."""

    prompt: str
    template: PromptTemplate
    parameters: Mapping[str, str]
    context: PromptContext
    record: PromptExecutionRecord
    truncated_fragments: tuple[ContextFragment, ...]
