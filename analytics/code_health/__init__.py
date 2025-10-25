"""Code health analytics package.

This module provides a high-level API for collecting and exposing code quality
metrics across the TradePulse repository.  The primary entry point is the
:class:`CodeMetricAggregator` which orchestrates AST analysis, git history
inspection, and downstream presentation layers (dashboards, API, widgets).
"""

from .aggregator import CodeMetricAggregator
from .models import (
    DeveloperMetrics,
    FileMetrics,
    FunctionMetrics,
    RepositoryMetrics,
    RiskProfile,
    Thresholds,
    TrendInsight,
)

__all__ = [
    "CodeMetricAggregator",
    "DeveloperMetrics",
    "FileMetrics",
    "FunctionMetrics",
    "RepositoryMetrics",
    "RiskProfile",
    "Thresholds",
    "TrendInsight",
]
