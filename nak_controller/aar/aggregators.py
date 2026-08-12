# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Aggregation utilities for AAR (Acceptor of Action Result).

This module provides aggregation mechanisms for error signals:
- Sliding window statistics (mean, std, min, max)
- Strategy-level aggregation
- Mode-level aggregation (GREEN/AMBER/RED)
- Catastrophic error rate tracking

See nak_controller/docs/AAR_SPEC.md for full specification.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

from .types import AAREntry, ErrorSignal


@dataclass
class AggregateStats:
    """Aggregated statistics over a collection of error signals.

    Attributes:
        count: Number of samples in the aggregate.
        mean: Mean normalized error.
        std: Standard deviation of normalized errors.
        min_error: Minimum normalized error observed.
        max_error: Maximum normalized error observed.
        positive_count: Number of positive errors (better than expected).
        negative_count: Number of negative errors (worse than expected).
        catastrophic_count: Number of errors exceeding threshold.
        catastrophic_rate: Proportion of catastrophic errors.
    """

    count: int = 0
    mean: float = 0.0
    std: float = 0.0
    min_error: float = 0.0
    max_error: float = 0.0
    positive_count: int = 0
    negative_count: int = 0
    catastrophic_count: int = 0
    catastrophic_rate: float = 0.0


@dataclass
class SlidingWindowAggregator:
    """Maintains rolling statistics over a fixed-size window of error signals.

    This aggregator uses a sliding window approach to compute statistics
    over the most recent N error signals, providing adaptive response
    to changing prediction accuracy.

    Attributes:
        window_size: Maximum number of entries to retain.
        catastrophic_threshold: Absolute error threshold for catastrophic classification.

    Example:
        >>> agg = SlidingWindowAggregator(window_size=100)
        >>> agg.add(error_signal)
        >>> stats = agg.get_stats()
        >>> print(f"Mean error: {stats.mean:.4f}")
    """

    window_size: int = 100
    catastrophic_threshold: float = 0.8
    _errors: Deque[float] = field(default_factory=lambda: deque())
    _signs: Deque[int] = field(default_factory=lambda: deque())
    _abs_errors: Deque[float] = field(default_factory=lambda: deque())

    def __post_init__(self) -> None:
        """Initialize internal deques with max length."""
        self._errors = deque(maxlen=self.window_size)
        self._signs = deque(maxlen=self.window_size)
        self._abs_errors = deque(maxlen=self.window_size)

    def add(self, error_signal: ErrorSignal) -> None:
        """Add a new error signal to the window.

        Args:
            error_signal: The error signal to add.
        """
        self._errors.append(error_signal.normalized_error)
        self._signs.append(error_signal.sign)
        self._abs_errors.append(error_signal.absolute_error)

    def get_stats(self) -> AggregateStats:
        """Compute aggregate statistics over the current window.

        Returns:
            AggregateStats with computed metrics.
        """
        if not self._errors:
            return AggregateStats()

        n = len(self._errors)
        errors_list = list(self._errors)
        signs_list = list(self._signs)
        abs_errors_list = list(self._abs_errors)

        mean = sum(errors_list) / n
        # Use sample variance (n-1) for unbiased estimation
        variance = sum((e - mean) ** 2 for e in errors_list) / (n - 1) if n > 1 else 0.0
        std = math.sqrt(variance)

        min_err = min(errors_list)
        max_err = max(errors_list)

        positive = sum(1 for s in signs_list if s > 0)
        negative = sum(1 for s in signs_list if s < 0)

        catastrophic = sum(1 for ae in abs_errors_list if ae > self.catastrophic_threshold)
        catastrophic_rate = catastrophic / n if n > 0 else 0.0

        return AggregateStats(
            count=n,
            mean=mean,
            std=std,
            min_error=min_err,
            max_error=max_err,
            positive_count=positive,
            negative_count=negative,
            catastrophic_count=catastrophic,
            catastrophic_rate=catastrophic_rate,
        )

    def clear(self) -> None:
        """Clear all entries from the window."""
        self._errors.clear()
        self._signs.clear()
        self._abs_errors.clear()


@dataclass
class StrategyAggregator:
    """Aggregates error signals by strategy ID.

    Maintains separate sliding windows for each strategy to track
    per-strategy prediction accuracy and error trends.

    Attributes:
        window_size: Window size for per-strategy aggregators.
        catastrophic_threshold: Threshold for catastrophic error classification.
    """

    window_size: int = 100
    catastrophic_threshold: float = 0.8
    _aggregators: dict[str, SlidingWindowAggregator] = field(default_factory=dict)

    def add(self, entry: AAREntry) -> None:
        """Add an AAR entry, routing to the appropriate strategy aggregator.

        Args:
            entry: The AAR entry containing action and error signal.
        """
        strategy_id = entry.action.strategy_id
        if strategy_id not in self._aggregators:
            self._aggregators[strategy_id] = SlidingWindowAggregator(
                window_size=self.window_size,
                catastrophic_threshold=self.catastrophic_threshold,
            )
        self._aggregators[strategy_id].add(entry.error_signal)

    def get_stats(self, strategy_id: str) -> AggregateStats:
        """Get aggregated stats for a specific strategy.

        Args:
            strategy_id: The strategy to query.

        Returns:
            AggregateStats for the strategy, or empty stats if not found.
        """
        if strategy_id not in self._aggregators:
            return AggregateStats()
        return self._aggregators[strategy_id].get_stats()

    def get_all_stats(self) -> dict[str, AggregateStats]:
        """Get aggregated stats for all strategies.

        Returns:
            Dictionary mapping strategy IDs to their stats.
        """
        return {sid: agg.get_stats() for sid, agg in self._aggregators.items()}

    def get_strategy_ids(self) -> list[str]:
        """Get list of all tracked strategy IDs.

        Returns:
            List of strategy IDs.
        """
        return list(self._aggregators.keys())


@dataclass
class ModeAggregator:
    """Aggregates error signals by system mode (GREEN/AMBER/RED).

    Tracks prediction accuracy across different operating modes to
    identify if certain modes produce more prediction errors.

    Attributes:
        window_size: Window size for per-mode aggregators.
        catastrophic_threshold: Threshold for catastrophic error classification.
    """

    window_size: int = 100
    catastrophic_threshold: float = 0.8
    _aggregators: dict[str, SlidingWindowAggregator] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize aggregators for known modes."""
        for mode in ["GREEN", "AMBER", "RED"]:
            self._aggregators[mode] = SlidingWindowAggregator(
                window_size=self.window_size,
                catastrophic_threshold=self.catastrophic_threshold,
            )

    def add(self, entry: AAREntry, mode: str) -> None:
        """Add an AAR entry to the appropriate mode aggregator.

        Args:
            entry: The AAR entry.
            mode: The system mode at the time of action ("GREEN", "AMBER", "RED").
        """
        if mode not in self._aggregators:
            self._aggregators[mode] = SlidingWindowAggregator(
                window_size=self.window_size,
                catastrophic_threshold=self.catastrophic_threshold,
            )
        self._aggregators[mode].add(entry.error_signal)

    def get_stats(self, mode: str) -> AggregateStats:
        """Get aggregated stats for a specific mode.

        Args:
            mode: The mode to query ("GREEN", "AMBER", "RED").

        Returns:
            AggregateStats for the mode, or empty stats if not found.
        """
        if mode not in self._aggregators:
            return AggregateStats()
        return self._aggregators[mode].get_stats()

    def get_all_stats(self) -> dict[str, AggregateStats]:
        """Get aggregated stats for all modes.

        Returns:
            Dictionary mapping modes to their stats.
        """
        return {mode: agg.get_stats() for mode, agg in self._aggregators.items()}


__all__ = [
    "AggregateStats",
    "SlidingWindowAggregator",
    "StrategyAggregator",
    "ModeAggregator",
]
