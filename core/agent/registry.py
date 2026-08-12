# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Agent registry for runtime trading agents."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, MutableMapping, NoReturn, cast

AgentFactory = Callable[..., object]


def _missing_agent_factory(*_: object, **__: object) -> NoReturn:
    raise RuntimeError(
        "MisanthropicAgent is unavailable because torch or its native dependencies "
        "are not installed. Install torch (e.g. `pip install torch`) to enable this "
        "agent."
    )


try:  # Optional heavy dependency; torch can raise ImportError/OSError when libs are missing
    from runtime.misanthropic_agent import MisanthropicAgent as _ImportedMisanthropicAgent
except (ImportError, OSError) as exc:  # pragma: no cover - exercised when torch is absent/broken
    MisanthropicAgent: type[object] | None = None
    _misanthropic_factory: AgentFactory = _missing_agent_factory
    _HAS_MISANTHROPIC_AGENT = False
    _IMPORT_ERROR = exc
else:
    MisanthropicAgent = _ImportedMisanthropicAgent
    _misanthropic_factory = cast(AgentFactory, _ImportedMisanthropicAgent)
    _HAS_MISANTHROPIC_AGENT = True
    _IMPORT_ERROR = None


class AgentRegistryError(RuntimeError):
    """Raised when an agent lookup fails."""


@dataclass(slots=True)
class AgentSpec:
    name: str
    factory: AgentFactory


class AgentRegistry:
    """Runtime registry that resolves agent factories by name."""

    def __init__(self) -> None:
        self._registry: MutableMapping[str, AgentFactory] = {}

    def register(self, name: str, factory: AgentFactory) -> None:
        key = name.lower()
        if key in self._registry:
            raise AgentRegistryError(f"agent '{name}' already registered")
        self._registry[key] = factory

    def override(self, name: str, factory: AgentFactory) -> None:
        self._registry[name.lower()] = factory

    def resolve(self, name: str) -> AgentFactory:
        try:
            return self._registry[name.lower()]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AgentRegistryError(f"unknown agent '{name}'") from exc

    def list_agents(self) -> Iterable[AgentSpec]:
        for name, factory in self._registry.items():
            yield AgentSpec(name=name, factory=factory)

    def update(self, entries: Mapping[str, AgentFactory]) -> None:
        for name, factory in entries.items():
            self._registry[name.lower()] = factory


def global_agent_registry() -> AgentRegistry:
    return _GLOBAL_REGISTRY


_GLOBAL_REGISTRY = AgentRegistry()

if _HAS_MISANTHROPIC_AGENT:
    _GLOBAL_REGISTRY.register("misanthropic", _misanthropic_factory)
else:  # pragma: no cover - depends on optional torch availability
    logging.getLogger(__name__).debug(
        "Skipping misanthropic agent registration (torch unavailable): %s",
        _IMPORT_ERROR,
    )
