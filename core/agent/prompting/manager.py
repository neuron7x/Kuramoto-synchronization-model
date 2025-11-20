"""High level prompt management orchestrating rendering and experiments."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from string import Template
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from .exceptions import (
    PromptGuardrailViolation,
    PromptInjectionDetected,
    PromptTemplateNotFoundError,
)
from .library import PromptTemplateLibrary
from .models import (
    ContextFragment,
    PromptContext,
    PromptContextWindow,
    PromptExecutionRecord,
    PromptOutcome,
    PromptRenderResult,
    PromptTemplate,
)

__all__ = [
    "PromptSanitizer",
    "PromptRunObserver",
    "PromptManager",
]


@dataclass(frozen=True)
class _SecurityRule:
    pattern: re.Pattern[str]
    message: str


class PromptSanitizer:
    """Detect suspicious content and normalise inputs."""

    _RuleInput = str | tuple[str, str]

    _DEFAULT_RULES: tuple[_RuleInput, ...] = (
        (
            r"(?i)ignore\s+all\s+previous\s+instructions",
            "prompt injection directive detected",
        ),
        (
            r"(?i)ignore\s+previous\s+directions",
            "prompt injection directive detected",
        ),
        (r"(?i)forget\s+(the\s+)?rules", "prompt injection directive detected"),
        (r"(?i)system\s+prompt\s*:", "prompt injection directive detected"),
        (
            r"(?i)<\s*script",
            "possible cross-site scripting content detected",
        ),
        (
            r"(?i){[{%]",
            "potential prompt-injection content detected",
        ),
    )

    _SECURITY_RULES: tuple[_RuleInput, ...] = (
        (
            r"(?i)(?:;\s*(?:drop|delete|truncate)\s+\w+|union\s+select|or\s+1=1|"
            r"or\s+'1'='1|--\s|/\*|\bxp_cmdshell\b)",
            "input appears to contain a SQL injection payload",
        ),
        (
            r"(?i)<\s*(?:script|img|svg|iframe|object|embed)[^>]*"
            r"(?:on\w+\s*=|src\s*=\s*['\"]?javascript:|href\s*=\s*['\"]?javascript:)",
            "possible cross-site scripting content detected",
        ),
        (
            r"(?i)<\s*form[^>]+action\s*=\s*['\"]?https?://",
            "input resembles a cross-site request forgery payload",
        ),
        (
            r"(?i)(?:pickle\.loads\(|yaml\.load\(|jsonpickle\.decode\(|"
            r"__import__\(|marshal\.loads\(|eval\(|exec\()",
            "unsafe dynamic deserialization directive detected",
        ),
        (
            r"(?is)<!DOCTYPE\s+[^>]*\[\s*<!ENTITY\s+[^>]*SYSTEM",
            "input includes XML entity declarations that can trigger entity expansion",
        ),
        (
            r"(?i)(?:\.\./|\.\.\\|%2e%2e%2f|%2e%2e\\)",
            "path traversal sequence detected in input",
        ),
        (
            r"(?i)(?:\blc_(?:all|ctype|collate|numeric|time|monetary)\s*=|"
            r"\blang(?:uage)?\s*=|locale\.setlocale\()",
            "locale override directives are not permitted",
        ),
    )

    def __init__(
        self,
        blocked_patterns: Iterable[_RuleInput] | None = None,
        *,
        max_length: int = 8000,
    ) -> None:
        rules = tuple(blocked_patterns or self._DEFAULT_RULES)
        self._custom_rules = tuple(self._compile_rule(entry) for entry in rules)
        self._security_rules = tuple(
            self._compile_rule(entry) for entry in self._SECURITY_RULES
        )
        self._max_length = max_length

    @staticmethod
    def _compile_rule(entry: _RuleInput) -> _SecurityRule:
        if isinstance(entry, tuple):
            pattern, message = entry
        else:
            pattern = entry
            message = "potential prompt-injection content detected"
        return _SecurityRule(re.compile(pattern), message)

    @staticmethod
    def _coerce_to_text(value: Any) -> str:
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise PromptInjectionDetected("binary payloads are not permitted")
        return str(value)

    @staticmethod
    def _ensure_utf8(text: str) -> None:
        try:
            text.encode("utf-8", "strict")
        except UnicodeEncodeError as exc:  # pragma: no cover - defensive guard
            raise PromptInjectionDetected("input must be valid UTF-8 text") from exc

    def sanitize_text(self, value: Any, *, strip: bool = False) -> str:
        text = self._coerce_to_text(value)
        if strip:
            text = text.strip()
        try:
            text = unicodedata.normalize("NFC", text)
        except ValueError as exc:
            raise PromptInjectionDetected("input must be valid UTF-8 text") from exc
        self._ensure_utf8(text)
        if len(text) > self._max_length:
            raise PromptInjectionDetected("input exceeds maximum supported length")
        if any(ord(char) < 32 and char not in (9, 10, 13) for char in text):
            raise PromptInjectionDetected("control characters are not permitted")
        for rule in (*self._security_rules, *self._custom_rules):
            if rule.pattern.search(text):
                raise PromptInjectionDetected(rule.message)
        return text

    def sanitize_mapping(self, mapping: Mapping[str, Any]) -> dict[str, str]:
        sanitized: dict[str, str] = {}
        for key, value in mapping.items():
            if not isinstance(key, str) or not key.strip():
                raise PromptInjectionDetected(
                    "parameter names must be non-empty strings"
                )
            sanitized[key.strip()] = self.sanitize_text(value)
        return sanitized

    def sanitize_fragment(self, fragment: ContextFragment) -> ContextFragment:
        return ContextFragment(
            label=self.sanitize_text(fragment.label, strip=True),
            content=self.sanitize_text(fragment.content),
            priority=fragment.priority,
            allow_truncate=fragment.allow_truncate,
            min_chars=fragment.min_chars,
        )


class PromptRunObserver:
    """Observer invoked when prompts are rendered or outcomes reported."""

    def on_render(
        self, record: PromptExecutionRecord
    ) -> None:  # pragma: no cover - hook
        del record

    def on_outcome(
        self, record_id: str, outcome: PromptOutcome
    ) -> None:  # pragma: no cover - hook
        del record_id, outcome


class PromptManager:
    """Facade offering rendering, experiment management and logging."""

    def __init__(
        self,
        library: PromptTemplateLibrary | None = None,
        *,
        sanitizer: PromptSanitizer | None = None,
        observers: Sequence[PromptRunObserver] | None = None,
        default_window: PromptContextWindow | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._library = library or PromptTemplateLibrary()
        self._sanitizer = sanitizer or PromptSanitizer()
        self._observers = tuple(observers or ())
        self._default_window = default_window or PromptContextWindow(max_chars=4096)
        self._logger = logger or logging.getLogger("tradepulse.prompting")
        self._records: MutableMapping[str, tuple[str, str]] = {}

    @property
    def library(self) -> PromptTemplateLibrary:
        return self._library

    def render(
        self,
        family: str,
        *,
        parameters: Mapping[str, Any] | None = None,
        context: PromptContext | None = None,
        window: PromptContextWindow | None = None,
        variant_assignment: str | float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> PromptRenderResult:
        context = context or PromptContext()
        window = window or self._default_window
        raw_parameters = parameters or {}

        sanitized_parameters = self._sanitizer.sanitize_mapping(raw_parameters)
        assignment_value = self._compute_assignment_value(
            family, sanitized_parameters, variant_assignment
        )
        template = self._library.select_template(family, assignment=assignment_value)
        template.validate_parameters(sanitized_parameters)
        sanitized_context = self._sanitize_context(context)
        template.apply_guardrails(sanitized_parameters, sanitized_context)

        base_prompt = self._render_template(template, sanitized_parameters)
        final_prompt, included, truncated = self._assemble_prompt(
            base_prompt, sanitized_context, window
        )

        record_id = self._build_record_id(
            template, sanitized_parameters, sanitized_context, final_prompt
        )
        record = PromptExecutionRecord.create(
            record_id=record_id,
            template=template,
            prompt_text=final_prompt,
            parameters=sanitized_parameters,
            included=included,
            truncated=truncated,
            metadata=metadata,
        )
        result = PromptRenderResult(
            prompt=final_prompt,
            template=template,
            parameters=sanitized_parameters,
            context=sanitized_context,
            record=record,
            truncated_fragments=tuple(truncated),
        )
        self._records[record.record_id] = (template.family, template.variant)
        self._notify_render(record)
        self._logger.info(
            "prompt.rendered",  # structured logging style
            extra={
                "template_family": template.family,
                "template_variant": template.variant,
                "template_version": template.version,
                "record_id": record.record_id,
            },
        )
        return result

    def record_outcome(self, record_id: str, outcome: PromptOutcome) -> bool:
        try:
            family, variant = self._records[record_id]
        except KeyError as exc:
            raise PromptTemplateNotFoundError(
                f"Unknown record identifier '{record_id}'"
            ) from exc
        try:
            rollback = self._library.record_outcome(family, variant, outcome)
            self._notify_outcome(record_id, outcome)
            self._logger.info(
                "prompt.outcome",
                extra={
                    "record_id": record_id,
                    "template_family": family,
                    "template_variant": variant,
                    "success": outcome.success,
                    "effect": outcome.effect,
                    "rollback": rollback,
                },
            )
            return rollback
        finally:
            self._records.pop(record_id, None)

    # ------------------------------------------------------------------
    # Internal helpers
    def _sanitize_context(self, context: PromptContext) -> PromptContext:
        sanitized_fragments = tuple(
            self._sanitizer.sanitize_fragment(fragment)
            for fragment in context.sorted_fragments()
        )
        return PromptContext(fragments=sanitized_fragments, metadata=context.metadata)

    def _render_template(
        self, template: PromptTemplate, parameters: Mapping[str, str]
    ) -> str:
        try:
            return Template(template.content).substitute(parameters)
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise PromptGuardrailViolation(
                f"Missing template placeholder: {exc.args[0]}"
            ) from exc

    def _assemble_prompt(
        self,
        base_prompt: str,
        context: PromptContext,
        window: PromptContextWindow,
    ) -> tuple[str, tuple[ContextFragment, ...], tuple[ContextFragment, ...]]:
        prompt = base_prompt
        if len(prompt) > window.max_chars:
            raise PromptGuardrailViolation(
                "base prompt exceeds the configured context window"
            )
        included: list[ContextFragment] = []
        truncated: list[ContextFragment] = []
        current_length = len(prompt)
        for fragment in context.fragments:
            prefix, content = self._fragment_components(fragment, window.separator)
            formatted_length = len(prefix) + len(content)
            projected = current_length + len(window.separator) + formatted_length
            if projected <= window.max_chars:
                prompt += window.separator + prefix + content
                current_length = projected
                included.append(fragment)
                continue
            if not fragment.allow_truncate:
                truncated.append(fragment.truncated(0))
                continue
            max_additional = window.max_chars - current_length - len(window.separator)
            if max_additional <= 0:
                truncated.append(fragment.truncated(0))
                continue
            available_for_content = max_additional - len(prefix)
            if available_for_content <= 0:
                truncated.append(fragment.truncated(0))
                continue
            truncated_fragment = fragment.truncated(available_for_content)
            t_prefix, t_content = self._fragment_components(
                truncated_fragment, window.separator
            )
            total_additional = len(t_prefix) + len(t_content)
            if total_additional > max_additional:
                excess = total_additional - max_additional
                if excess >= len(t_content):
                    truncated.append(fragment.truncated(0))
                    continue
                truncated_fragment = truncated_fragment.truncated(
                    len(t_content) - excess
                )
                t_prefix, t_content = self._fragment_components(
                    truncated_fragment, window.separator
                )
            prompt += window.separator + t_prefix + t_content
            current_length += len(window.separator) + len(t_prefix) + len(t_content)
            included.append(truncated_fragment)
            truncated.append(truncated_fragment)
        return prompt, tuple(included), tuple(truncated)

    def _fragment_components(
        self, fragment: ContextFragment, separator: str
    ) -> tuple[str, str]:
        content = fragment.content.strip()
        if not content:
            return fragment.label, ""
        if "\n" in content:
            return f"{fragment.label}:{separator}", content
        return f"{fragment.label}: ", content

    def _build_record_id(
        self,
        template: PromptTemplate,
        parameters: Mapping[str, str],
        context: PromptContext,
        prompt: str,
    ) -> str:
        digest = sha256()
        digest.update(template.family.encode("utf-8"))
        digest.update(template.variant.encode("utf-8"))
        digest.update(template.version.encode("utf-8"))
        for key in sorted(parameters):
            digest.update(key.encode("utf-8"))
            digest.update(parameters[key].encode("utf-8"))
        for fragment in context.fragments:
            digest.update(fragment.label.encode("utf-8"))
            digest.update(fragment.content.encode("utf-8"))
        digest.update(str(len(prompt)).encode("ascii"))
        return digest.hexdigest()[:16]

    def _compute_assignment_value(
        self,
        family: str,
        parameters: Mapping[str, str],
        variant_assignment: str | float | None,
    ) -> float | None:
        if variant_assignment is None and not parameters:
            return None
        if isinstance(variant_assignment, float):
            if not 0.0 <= variant_assignment < 1.0:
                raise PromptGuardrailViolation(
                    "variant assignment floats must be within [0, 1)"
                )
            return variant_assignment
        seed_material = family
        if variant_assignment is not None:
            seed_material += f"|{variant_assignment}"
        else:
            payload = json.dumps(parameters, sort_keys=True)
            seed_material += f"|{payload}"
        digest = sha256(seed_material.encode("utf-8")).digest()
        number = int.from_bytes(digest[:8], "big")
        return (number % 10_000_000_000) / 10_000_000_000

    def _notify_render(self, record: PromptExecutionRecord) -> None:
        for observer in self._observers:
            try:
                observer.on_render(record)
            except Exception:  # pragma: no cover - defensive branch
                self._logger.exception("prompt.observer.render-failed")

    def _notify_outcome(self, record_id: str, outcome: PromptOutcome) -> None:
        for observer in self._observers:
            try:
                observer.on_outcome(record_id, outcome)
            except Exception:  # pragma: no cover - defensive branch
                self._logger.exception("prompt.observer.outcome-failed")
