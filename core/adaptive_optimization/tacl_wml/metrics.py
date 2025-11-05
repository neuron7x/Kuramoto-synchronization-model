"""Telemetry metrics with implementation shortfall tracking."""

from dataclasses import dataclass
from typing import List


def percentile(xs: List[float], p: float) -> float:
    """Calculate percentile of a list of values."""
    if not xs:
        return 0.0
    xs_sorted = sorted(xs)
    k = (len(xs_sorted) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(xs_sorted) - 1)
    if f == c:
        return float(xs_sorted[int(k)])
    d0 = xs_sorted[f] * (c - k)
    d1 = xs_sorted[c] * (k - f)
    return float(d0 + d1)


@dataclass(slots=True)
class Telemetry:
    """Performance telemetry for a hot path."""

    latency_ms: List[float]
    resource_cost: float
    pnl_delta: float
    vol_index: float
    is_bp: float = 0.0  # NEW: implementation shortfall (basis points)

    def __post_init__(self) -> None:
        """Validate and normalize values."""
        self.latency_ms = [max(0.0, float(x)) for x in self.latency_ms]
        self.resource_cost = max(0.0, float(self.resource_cost))
        self.pnl_delta = float(self.pnl_delta)
        self.vol_index = max(0.0, float(self.vol_index))
        self.is_bp = float(self.is_bp)

    @property
    def p50(self) -> float:
        """Median latency."""
        return percentile(self.latency_ms, 50)

    @property
    def p99(self) -> float:
        """99th percentile latency."""
        return percentile(self.latency_ms, 99)

    @property
    def jitter(self) -> float:
        """Latency jitter (p99 - p50)."""
        return max(0.0, self.p99 - self.p50)
