"""Backtesting utilities, strategies, and performance analytics."""

from .engine import LatencyConfig, OrderBookConfig
from .performance import (
    PerformanceReport,
    compute_performance_metrics,
    export_performance_report,
)
from .synthetic import (
    ControlledExperiment,
    LiquidityShock,
    OrderBookDepthConfig,
    OrderBookDepthProfile,
    StrategyEvaluation,
    StructuralBreak,
    SyntheticScenario,
    SyntheticScenarioConfig,
    SyntheticScenarioGenerator,
    VolatilityShift,
)

__all__ = [
    "LatencyConfig",
    "OrderBookConfig",
    "ControlledExperiment",
    "LiquidityShock",
    "OrderBookDepthConfig",
    "OrderBookDepthProfile",
    "StrategyEvaluation",
    "StructuralBreak",
    "SyntheticScenario",
    "SyntheticScenarioConfig",
    "SyntheticScenarioGenerator",
    "VolatilityShift",
    "PerformanceReport",
    "compute_performance_metrics",
    "export_performance_report",
]
