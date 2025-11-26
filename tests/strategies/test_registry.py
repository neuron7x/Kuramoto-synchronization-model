"""Tests for the strategy registry infrastructure."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from strategies.registry import StrategyRegistry, StrategySpec, UnknownStrategyError


def _dummy_factory(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {"config": dict(config or {})}


def _entrypoint(name: str) -> str:
    module = __name__
    return f"{module}:{name}"


def test_register_and_create_strategy() -> None:
    registry = StrategyRegistry()
    registry.register("dummy", _entrypoint("_dummy_factory"))

    instance = registry.create("dummy", {"foo": "bar"})

    assert instance["config"] == {"foo": "bar"}


def test_register_prevents_duplicates() -> None:
    registry = StrategyRegistry()
    registry.register("dup", _entrypoint("_dummy_factory"))

    with pytest.raises(ValueError):
        registry.register("dup", _entrypoint("_dummy_factory"))


def test_override_updates_factory() -> None:
    registry = StrategyRegistry()

    registry.register("switch", _entrypoint("_dummy_factory"))
    registry.register("switch", _entrypoint("_other_factory"), override=True)

    instance = registry.create("switch")
    assert instance["alt"] is True


def _other_factory(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {"alt": True, "config": dict(config or {})}


def test_available_returns_sorted_specs() -> None:
    registry = StrategyRegistry()
    registry.register("beta", _entrypoint("_dummy_factory"))
    registry.register("alpha", _entrypoint("_dummy_factory"), override=True)
    # Re-register alpha with override to ensure deterministic metadata update.

    specs = registry.available()

    assert isinstance(specs, tuple)
    assert [spec.name for spec in specs] == ["alpha", "beta"]
    assert all(isinstance(spec, StrategySpec) for spec in specs)


def test_unknown_strategy_error() -> None:
    registry = StrategyRegistry()

    with pytest.raises(UnknownStrategyError):
        registry.get("missing")

    with pytest.raises(UnknownStrategyError):
        registry.create("missing")


def test_strategy_spec_load_factory_returns_callable() -> None:
    registry = StrategyRegistry()
    registry.register("dummy", _entrypoint("_dummy_factory"))

    spec = registry.get("dummy")
    factory = spec.load_factory()

    assert callable(factory)
    assert factory({"value": 1}) == {"config": {"value": 1}}


def test_package_list_strategies_exposes_quantum_neural() -> None:
    import strategies

    names = [spec.name for spec in strategies.list_strategies()]

    assert "quantum_neural" in names
