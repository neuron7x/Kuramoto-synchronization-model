"""Strategy modules for TradePulse."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from .neuro_trade_pulse import NeuroTradePulseConfig, NeuroTradePulseStrategy
from .registry import (
    StrategyRegistry,
    StrategySpec,
    UnknownStrategyError,
    register_strategy,
    resolve_strategy,
)
from .registry import available_strategies as _available_strategies


def get_strategy(name: str, config: Dict[str, Any] | None = None) -> Any:
    """Resolve a registered strategy by *name*."""

    try:
        return resolve_strategy(name, config)
    except UnknownStrategyError as exc:  # pragma: no cover - defensive guard
        available = ", ".join(spec.name for spec in _available_strategies())
        raise ValueError(
            f"Unknown strategy '{name}'. Available: [{available}]"
        ) from exc


def list_strategies() -> Tuple[StrategySpec, ...]:
    """Return metadata for the registered strategies."""

    return _available_strategies()


# Register built-in strategies ---------------------------------------------------

register_strategy(
    "quantum_neural",
    "strategies.quantum_neural:get_strategy",
    description="Hybrid LSTM/Transformer model with risk-managed backtesting.",
)


__all__ = [
    "NeuroTradePulseConfig",
    "NeuroTradePulseStrategy",
    "StrategyRegistry",
    "StrategySpec",
    "UnknownStrategyError",
    "get_strategy",
    "list_strategies",
    "register_strategy",
]
