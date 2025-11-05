"""Telemetry metrics with implementation shortfall tracking."""

from dataclasses import dataclass
from typing import List


def percentile(xs: List[float], p: float) -> float:
    """Calculate percentile of a list of values using linear interpolation.

    Args:
        xs: List of numeric values
        p: Percentile to calculate (0-100)

    Returns:
        Calculated percentile value

    Raises:
        ValueError: If percentile is not in range [0, 100]
    """
    if not 0 <= p <= 100:
        raise ValueError(f"Percentile must be in range [0, 100], got {p}")

    if not xs:
        return 0.0

    if len(xs) == 1:
        return float(xs[0])

    # Use sorted copy to avoid mutating input
    xs_sorted = sorted(xs)
    k = (len(xs_sorted) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(xs_sorted) - 1)

    if f == c:
        return float(xs_sorted[f])

    # Linear interpolation between f and c
    return float(xs_sorted[f] * (c - k) + xs_sorted[c] * (k - f))


@dataclass(slots=True)
class Telemetry:
    """Performance telemetry for a hot path.

    Attributes:
        latency_ms: List of latency measurements in milliseconds
        resource_cost: Resource cost metric (normalized, >= 0)
        pnl_delta: PnL change indicator
        vol_index: Volatility index (0-1 typically)
        is_bp: Implementation shortfall in basis points (>= 0)
    """

    latency_ms: List[float]
    resource_cost: float
    pnl_delta: float
    vol_index: float
    is_bp: float = 0.0

    def __post_init__(self) -> None:
        """Validate and normalize values.

        Raises:
            ValueError: If latency_ms is empty or contains invalid values
        """
        if not self.latency_ms:
            raise ValueError("latency_ms cannot be empty")

        # Validate and normalize latency values
        self.latency_ms = [max(0.0, float(x)) for x in self.latency_ms]
        self.resource_cost = max(0.0, float(self.resource_cost))
        self.pnl_delta = float(self.pnl_delta)
        self.vol_index = max(0.0, float(self.vol_index))
        self.is_bp = max(0.0, float(self.is_bp))  # IS should be non-negative

    @property
    def p50(self) -> float:
        """Median latency (50th percentile)."""
        return percentile(self.latency_ms, 50)

    @property
    def p99(self) -> float:
        """99th percentile latency."""
        return percentile(self.latency_ms, 99)

    @property
    def jitter(self) -> float:
        """Latency jitter (p99 - p50), measures variability."""
        return max(0.0, self.p99 - self.p50)

    @property
    def mean(self) -> float:
        """Mean latency."""
        return sum(self.latency_ms) / len(self.latency_ms) if self.latency_ms else 0.0
