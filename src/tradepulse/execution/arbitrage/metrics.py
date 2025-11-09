"""Advanced metrics utilities supporting arbitrage operations."""

from __future__ import annotations

from bisect import bisect_left, insort
from collections import deque
from datetime import timedelta
from typing import Deque, Iterable


class LatencyTracker:
    """Maintains rolling latency statistics with percentile queries."""

    __slots__ = ("_samples", "_sorted", "_maxlen")

    def __init__(self, *, max_samples: int = 2048) -> None:
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        self._samples: Deque[float] = deque(maxlen=max_samples)
        self._sorted: list[float] = []
        self._maxlen = max_samples

    def record(self, latency: timedelta) -> None:
        """Record a new latency observation."""

        if latency < timedelta(0):
            raise ValueError("latency cannot be negative")
        seconds = latency.total_seconds()
        if len(self._samples) == self._maxlen:
            oldest = self._samples.popleft()
            index = bisect_left(self._sorted, oldest)
            # Defensive guard; the value should always be present
            if index < len(self._sorted) and self._sorted[index] == oldest:
                self._sorted.pop(index)
        self._samples.append(seconds)
        insort(self._sorted, seconds)

    def percentile(self, percentile: float) -> timedelta:
        """Return the percentile latency as a timedelta."""

        if not 0.0 <= percentile <= 100.0:
            raise ValueError("percentile must be between 0 and 100")
        if not self._sorted:
            return timedelta(0)
        rank = (percentile / 100.0) * (len(self._sorted) - 1)
        lower_index = int(rank)
        upper_index = min(lower_index + 1, len(self._sorted) - 1)
        weight = rank - lower_index
        lower_value = self._sorted[lower_index]
        upper_value = self._sorted[upper_index]
        interpolated = lower_value + (upper_value - lower_value) * weight
        return timedelta(seconds=interpolated)

    def average(self) -> timedelta:
        if not self._samples:
            return timedelta(0)
        return timedelta(seconds=sum(self._samples) / len(self._samples))

    def max_latency(self) -> timedelta:
        if not self._sorted:
            return timedelta(0)
        return timedelta(seconds=self._sorted[-1])

    def min_latency(self) -> timedelta:
        if not self._sorted:
            return timedelta(0)
        return timedelta(seconds=self._sorted[0])

    def __len__(self) -> int:
        return len(self._samples)

    def snapshot(self) -> tuple[timedelta, ...]:
        """Return a tuple of recorded samples for diagnostics."""

        return tuple(timedelta(seconds=value) for value in self._samples)

    def extend(self, latencies: Iterable[timedelta]) -> None:
        """Bulk record latency observations."""

        for latency in latencies:
            self.record(latency)
