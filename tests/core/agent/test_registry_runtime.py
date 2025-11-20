"""Tests for the runtime agent registry."""

from __future__ import annotations

import pytest

from core.agent import (
    AgentRegistry,
    AgentRegistryError,
    AgentSpec,
    global_agent_registry,
)
from runtime.misanthropic_agent import MisanthropicAgent


def test_global_registry_contains_misanthropic() -> None:
    registry = global_agent_registry()
    factory = registry.resolve("misanthropic")
    assert factory is MisanthropicAgent


def test_registry_register_and_override() -> None:
    registry = AgentRegistry()
    registry.register("demo", MisanthropicAgent)
    with pytest.raises(AgentRegistryError):
        registry.register("demo", MisanthropicAgent)

    registry.override("demo", MisanthropicAgent)
    factory = registry.resolve("demo")
    assert isinstance(factory(write_metrics=False), MisanthropicAgent)


def test_registry_list_agents() -> None:
    registry = AgentRegistry()
    registry.register("a", MisanthropicAgent)
    specs = list(registry.list_agents())
    assert any(isinstance(spec, AgentSpec) and spec.name == "a" for spec in specs)
