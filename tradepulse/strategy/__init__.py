"""Unified Strategy Engine API for TradePulse.

This module provides the base classes and contracts for building trading
strategies that work uniformly across backtest, paper, and live modes.

Core Components:
    - Strategy: Abstract base class for all strategies
    - StrategyEngine: Coordinates strategy execution
    - RiskEvaluator: Risk assessment protocol

See docs/ARCHITECTURE.md for system design details.
"""

from .base import (
    Strategy,
    StrategyProtocol,
    StrategyResult,
    StrategyConfig,
)
from .engine import (
    StrategyEngine,
    StrategyEngineConfig,
    StrategyEngineState,
)

__all__ = [
    # Base strategy classes
    "Strategy",
    "StrategyProtocol",
    "StrategyResult",
    "StrategyConfig",
    # Engine classes
    "StrategyEngine",
    "StrategyEngineConfig",
    "StrategyEngineState",
]
