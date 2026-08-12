# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Backtesting utilities, strategies, and performance analytics."""

from .dopamine_td import (
    DopamineTDParams,
    dopamine_td_signal,
    run_dopamine_backtest,
    run_vectorized_dopamine_td,
)
from .engine import LatencyConfig, OrderBookConfig
from .performance import PerformanceReport, compute_performance_metrics, export_performance_report
from .robustness_gates import DecisionLabel, RobustnessGateResult, evaluate_robustness_gates
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
    "DopamineTDParams",
    "dopamine_td_signal",
    "run_dopamine_backtest",
    "run_vectorized_dopamine_td",
    "DecisionLabel",
    "RobustnessGateResult",
    "evaluate_robustness_gates",
]
