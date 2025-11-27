"""Agent registry for runtime trading agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, MutableMapping

from runtime.misanthropic_agent import MisanthropicAgent
from tradepulse.core.neuro.neuro_physio_guard import NeuroPhysioGuard

AgentFactory = Callable[..., object]


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
_GLOBAL_REGISTRY.register("misanthropic", MisanthropicAgent)
_GLOBAL_REGISTRY.register("neuro_physio_guard", NeuroPhysioGuard)
