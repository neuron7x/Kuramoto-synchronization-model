"""Debug helpers for capturing structured runtime state snapshots."""

from __future__ import annotations

import inspect
import os
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

__all__ = ["VariableInspector"]

_REDACTED = "***redacted***"


class VariableInspector:
    """Collect and sanitise runtime variable snapshots for debugging."""

    def __init__(
        self,
        *,
        redact_patterns: Iterable[str] | None = None,
    ) -> None:
        patterns = tuple(
            pattern.lower()
            for pattern in (redact_patterns or ("secret", "token", "key", "password"))
        )
        # Preserve order while normalising duplicates.
        self._redact_patterns: tuple[str, ...] = tuple(dict.fromkeys(patterns))
        self._providers: dict[str, Callable[[], Any | Awaitable[Any]]] = {}

    @property
    def redact_patterns(self) -> tuple[str, ...]:
        """Return the configured redaction patterns."""

        return self._redact_patterns

    def register(self, name: str, provider: Callable[[], Any | Awaitable[Any]]) -> None:
        """Register a provider that returns the value for *name* when inspected."""

        if not name or not name.strip():  # pragma: no cover - defensive guard
            raise ValueError("Provider name must be a non-empty string")
        self._providers[name] = provider

    def unregister(self, name: str) -> None:
        """Remove the provider registered for *name* if present."""

        self._providers.pop(name, None)

    async def snapshot(self) -> dict[str, Any]:
        """Return a sanitised snapshot from all registered providers."""

        snapshot: dict[str, Any] = {}
        for name, provider in self._providers.items():
            try:
                value = provider()
                if inspect.isawaitable(value):
                    value = await value
            except Exception as exc:  # pragma: no cover - defensive fallback
                snapshot[name] = {"error": repr(exc)}
                continue
            snapshot[name] = self._sanitise((name,), value)
        return snapshot

    def collect_environment(self, variables: Sequence[str]) -> dict[str, str | None]:
        """Collect a mapping of selected environment variables."""

        entries: dict[str, str | None] = {}
        for variable in variables:
            key = variable.strip()
            if not key:
                continue
            entries[key] = os.environ.get(key)
        return entries

    def _should_redact(self, key: str) -> bool:
        lowered = key.lower()
        return any(pattern and pattern in lowered for pattern in self._redact_patterns)

    def _sanitise(self, path: Sequence[str], value: Any) -> Any:
        key = path[-1]
        if self._should_redact(key):
            return _REDACTED

        if value is None or isinstance(value, (bool, int, float, str)):
            return value

        if isinstance(value, Mapping):
            return {
                str(item_key): self._sanitise(path + (str(item_key),), item_value)
                for item_key, item_value in value.items()
            }

        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            return [
                self._sanitise(path + (str(index),), item)
                for index, item in enumerate(value)
            ]

        if is_dataclass(value):
            return self._sanitise(path, asdict(value))

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            try:
                dumped = model_dump()
            except Exception:  # pragma: no cover - defensive guard
                return repr(value)
            return self._sanitise(path, dumped)

        if hasattr(value, "dict") and callable(getattr(value, "dict")):
            try:
                dumped = value.dict()
            except Exception:  # pragma: no cover - defensive guard
                return repr(value)
            return self._sanitise(path, dumped)

        return repr(value)
