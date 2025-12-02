"""Unified decision loop for TradePulse.

This module provides the decision loop that works uniformly across
backtest, paper trading, and live execution modes. The loop coordinates:
    - Strategy signal generation
    - Risk evaluation and filtering
    - Action decision making
    - AAR feedback collection

See docs/DOMAIN_MODEL.md for architecture details.
"""

from .decision_loop import (
    DecisionLoop,
    DecisionLoopConfig,
    DecisionCycle,
    ExecutionAdapter,
    ExecutionResult,
    RiskEvaluator,
    AcceptAllRiskEvaluator,
    SimpleBacktestAdapter,
)

__all__ = [
    "DecisionLoop",
    "DecisionLoopConfig",
    "DecisionCycle",
    "ExecutionAdapter",
    "ExecutionResult",
    "RiskEvaluator",
    "AcceptAllRiskEvaluator",
    "SimpleBacktestAdapter",
]
