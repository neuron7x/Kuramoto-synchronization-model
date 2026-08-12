# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Strategy modules for GeoSync."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from .neuro_geosync import NeuroGeoSyncConfig, NeuroGeoSyncStrategy
from .registry import (
    MarketRegime,
    RiskLevel,
    StrategyRegistry,
    StrategyRouter,
    StrategyRoutingPolicy,
    StrategySpec,
    StrategyStateInput,
    SystemStress,
    UnknownStrategyError,
    default_routing_policy,
    global_router,
    register_strategy,
    resolve_strategy,
    route_strategy,
)
from .registry import (
    available_strategies as _available_strategies,
)


def get_strategy(name: str, config: Dict[str, Any] | None = None) -> Any:
    """Resolve a registered strategy by *name*."""

    try:
        return resolve_strategy(name, config)
    except UnknownStrategyError as exc:  # pragma: no cover - defensive guard
        available = ", ".join(spec.name for spec in _available_strategies())
        raise ValueError(f"Unknown strategy '{name}'. Available: [{available}]") from exc


def list_strategies() -> Tuple[StrategySpec, ...]:
    """Return metadata for the registered strategies."""

    return _available_strategies()


# Register built-in strategies ---------------------------------------------------

register_strategy(
    "quantum_neural",
    "strategies.quantum_neural:get_strategy",
    description="Hybrid LSTM/Transformer model with risk-managed backtesting.",
)
register_strategy(
    "neuro_geosync",
    "strategies.neuro_geosync:get_strategy",
    description="Composite signal + motivation engine for cautious regimes.",
)
# Backwards-compatible alias kept for consumers that still use the legacy name.
register_strategy(
    "neuro_trade",
    "strategies.neuro_geosync:get_strategy",
    description="Deprecated alias of ``neuro_geosync`` — kept for backwards compatibility.",
)


__all__ = [
    "NeuroGeoSyncConfig",
    "NeuroGeoSyncStrategy",
    "StrategyRegistry",
    "StrategySpec",
    "UnknownStrategyError",
    "StrategyRoutingPolicy",
    "StrategyRouter",
    "StrategyStateInput",
    "MarketRegime",
    "RiskLevel",
    "SystemStress",
    "default_routing_policy",
    "global_router",
    "get_strategy",
    "list_strategies",
    "register_strategy",
    "route_strategy",
]
