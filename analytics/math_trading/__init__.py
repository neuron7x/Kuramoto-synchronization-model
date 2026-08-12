# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical trading algorithms for optimization, dynamics, and risk management.

This module provides production-ready implementations of quantitative finance
algorithms for execution optimization, portfolio rebalancing, and position sizing.

Level 1: Optimization
    - Almgren-Chriss optimal execution model
    - Transaction cost-aware portfolio rebalancing
    - Multi-asset Kelly criterion

Example:
    >>> from analytics.math_trading import AlmgrenChrissOptimizer, OptimalExecutionParams
    >>> params = OptimalExecutionParams(
    ...     total_quantity=10000,
    ...     duration_seconds=3600,
    ...     volatility=0.02,
    ...     temporary_impact=0.001,
    ...     permanent_impact=0.0001,
    ...     risk_aversion=1e-6,
    ... )
    >>> optimizer = AlmgrenChrissOptimizer(params)
    >>> schedule = optimizer.compute_schedule(num_slices=10)
"""

from __future__ import annotations

from .kelly_criterion import (
    KellyCriterion,
    KellyParams,
    KellyResult,
    MultiAssetKelly,
    MultiAssetKellyParams,
    MultiAssetKellyResult,
    kelly_from_edge_variance,
)
from .optimal_execution import (
    AlmgrenChrissOptimizer,
    ExecutionSlice,
    OptimalExecutionParams,
    OptimalExecutionResult,
    compute_vwap_schedule,
)
from .portfolio_rebalancing import (
    PortfolioRebalancer,
    RebalanceConstraints,
    RebalanceRequest,
    RebalanceResult,
    TradeOrder,
    compute_minimum_variance_trades,
)

__all__ = [
    # Optimal Execution
    "AlmgrenChrissOptimizer",
    "ExecutionSlice",
    "OptimalExecutionParams",
    "OptimalExecutionResult",
    "compute_vwap_schedule",
    # Portfolio Rebalancing
    "PortfolioRebalancer",
    "RebalanceRequest",
    "RebalanceResult",
    "RebalanceConstraints",
    "TradeOrder",
    "compute_minimum_variance_trades",
    # Kelly Criterion
    "KellyCriterion",
    "KellyParams",
    "KellyResult",
    "MultiAssetKelly",
    "MultiAssetKellyParams",
    "MultiAssetKellyResult",
    "kelly_from_edge_variance",
]
