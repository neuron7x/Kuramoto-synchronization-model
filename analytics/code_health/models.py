# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Data models for the code health analytics domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Mapping


@dataclass(slots=True)
class Thresholds:
    """Configurable thresholds for code quality heuristics.

    The defaults are intentionally conservative and may be tuned per team.
    """

    max_function_length: int = 60
    max_cyclomatic_complexity: int = 10
    max_coupling: int = 15
    max_hotspot_churn: int = 20
    min_interface_stability: float = 0.75
    max_risk_score: float = 0.6


@dataclass(slots=True)
class FunctionMetrics:
    """AST-derived metrics for a single function."""

    name: str
    file_path: str
    start_line: int
    end_line: int
    cyclomatic_complexity: int
    length: int
    fan_in: int
    fan_out: int

    @property
    def exceeds_length(self) -> bool:
        return self.length > Thresholds().max_function_length

    @property
    def exceeds_complexity(self) -> bool:
        return self.cyclomatic_complexity > Thresholds().max_cyclomatic_complexity


@dataclass(slots=True)
class RiskProfile:
    """Represents risk derived from structural and historical signals."""

    risk_score: float
    contributing_factors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass(slots=True)
class FileMetrics:
    """Aggregated metrics for a single file."""

    path: str
    total_lines: int
    avg_cyclomatic_complexity: float
    max_cyclomatic_complexity: int
    functions: List[FunctionMetrics]
    coupling: int
    fan_in: int
    fan_out: int
    change_frequency: int
    interface_stability: float
    churn: int
    hot_spot_score: float
    risk_profile: RiskProfile

    def exceeding_thresholds(self, thresholds: Thresholds) -> Dict[str, float]:
        """Return any metrics that exceed configured thresholds."""

        violations: Dict[str, float] = {}
        if self.max_cyclomatic_complexity > thresholds.max_cyclomatic_complexity:
            violations["max_cyclomatic_complexity"] = self.max_cyclomatic_complexity
        if self.avg_cyclomatic_complexity > thresholds.max_cyclomatic_complexity:
            violations["avg_cyclomatic_complexity"] = self.avg_cyclomatic_complexity
        if self.coupling > thresholds.max_coupling:
            violations["coupling"] = self.coupling
        if self.hot_spot_score > thresholds.max_hotspot_churn:
            violations["hot_spot_score"] = self.hot_spot_score
        if self.interface_stability < thresholds.min_interface_stability:
            violations["interface_stability"] = self.interface_stability
        if self.risk_profile.risk_score > thresholds.max_risk_score:
            violations["risk_score"] = self.risk_profile.risk_score
        return violations


@dataclass(slots=True)
class TrendInsight:
    """Historical perspective for a metric."""

    metric: str
    previous: float
    current: float
    delta: float
    direction: str
    timestamp: datetime


@dataclass(slots=True)
class DeveloperMetrics:
    """Activity overview for an individual contributor."""

    author: str
    commits: int
    files_touched: int
    churn: int
    hotspots: List[str] = field(default_factory=list)


@dataclass(slots=True)
class RepositoryMetrics:
    """Aggregate code health picture for the repository."""

    generated_at: datetime
    files: Mapping[str, FileMetrics]
    thresholds: Thresholds
    risk_hotspots: List[FileMetrics] = field(default_factory=list)
    trends: List[TrendInsight] = field(default_factory=list)
    developer_metrics: List[DeveloperMetrics] = field(default_factory=list)

    def iter_files(self) -> Iterable[FileMetrics]:
        return self.files.values()

    def most_risky(self, limit: int = 10) -> List[FileMetrics]:
        return sorted(self.risk_hotspots, key=lambda fm: fm.risk_profile.risk_score, reverse=True)[
            :limit
        ]
