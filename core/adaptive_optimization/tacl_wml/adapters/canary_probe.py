"""Canary probe for testing tentative system states."""

import time
from typing import Callable, Optional
from ..wml import TelemetryProbe
from ..metrics import Telemetry
from ..actions import ActionPlan


class CanaryProbe(TelemetryProbe):
    """Probe that tests system performance with tentative parameters.

    Supports multiple modes:
    - callable: Execute a test function multiple times
    - synthetic: Use a model to predict performance
    """

    def __init__(
        self,
        mode: str = "callable",
        fn: Optional[Callable[[], None]] = None,
        samples: int = 16,
        timeout_s: float = 0.3,
        pnl_fn: Optional[Callable[[], float]] = None,
    ):
        """Initialize canary probe.

        Args:
            mode: "callable" or "synthetic"
            fn: Test function to execute (required for callable mode)
            samples: Number of samples to collect
            timeout_s: Timeout for canary tests
            pnl_fn: Function to compute PnL delta (optional)
        """
        self.mode = mode
        self.fn = fn
        self.samples = samples
        self.timeout_s = timeout_s
        self.pnl_fn = pnl_fn or (lambda: 0.0)

    def measure_after(
        self, path: str, tentative_myelin: float, plan: ActionPlan
    ) -> Telemetry:
        """Measure telemetry after hypothetically applying the plan.

        Args:
            path: Hot path identifier
            tentative_myelin: Proposed myelin value
            plan: Proposed action plan

        Returns:
            Predicted telemetry
        """
        if self.mode == "callable" and self.fn is not None:
            return self._measure_callable(tentative_myelin)
        else:
            return self._measure_synthetic(tentative_myelin)

    def _measure_callable(self, myelin: float) -> Telemetry:
        """Measure by executing the test function."""
        latencies = []
        start = time.time()

        for _ in range(self.samples):
            if time.time() - start > self.timeout_s:
                break

            t0 = time.perf_counter()
            if self.fn:
                self.fn()
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)

        # Use actual samples or estimate if timeout
        if not latencies:
            latencies = [10.0]  # Fallback estimate

        return Telemetry(
            latency_ms=latencies,
            resource_cost=0.5,  # Placeholder
            pnl_delta=self.pnl_fn(),
            vol_index=0.5,  # Placeholder
            is_bp=0.0,
        )

    def _measure_synthetic(self, myelin: float) -> Telemetry:
        """Synthesize telemetry based on myelin level.

        Higher myelin = better performance (lower latency, lower IS)
        """
        # Base latency decreases with myelin
        base = 12.0 - 6.0 * myelin
        latencies = [base * 0.6, base * 0.8, base * 0.9, base]

        # IS decreases with myelin (better execution quality)
        is_bp = max(0.0, 10.0 - 8.0 * myelin)

        return Telemetry(
            latency_ms=latencies,
            resource_cost=1.0,
            pnl_delta=0.0,
            vol_index=0.4,
            is_bp=is_bp,
        )
