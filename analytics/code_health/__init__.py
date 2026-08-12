# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Code health analytics package.

This module provides a high-level API for collecting and exposing code quality
metrics across the GeoSync repository.  The primary entry point is the
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
