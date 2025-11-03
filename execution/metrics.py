"""Prometheus metrics for risk controls and circuit breaker.

This module provides instrumentation for risk compliance checks,
circuit breaker state, and rejection reasons.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry

try:
    from prometheus_client import Counter, Gauge

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


__all__ = ["RiskMetrics", "get_risk_metrics"]


_GLOBAL_METRICS: Optional["RiskMetrics"] = None


class RiskMetrics:
    """Metrics collector for risk controls."""

    def __init__(self, registry: Optional["CollectorRegistry"] = None) -> None:
        """Initialize risk metrics.

        Args:
            registry: Prometheus registry (uses default if None)
        """
        self._registry = registry
        self._enabled = PROMETHEUS_AVAILABLE

        if not self._enabled:
            return

        kwargs = {"registry": registry} if registry else {}

        self.kill_switch = Gauge(
            "tradepulse_risk_kill_switch",
            "Global kill switch state (1=enabled, 0=disabled)",
            labelnames=["env"],
            **kwargs,
        )

        self.gross_exposure = Gauge(
            "tradepulse_risk_gross_exposure",
            "Current gross exposure in notional terms",
            labelnames=["env"],
            **kwargs,
        )

        self.daily_drawdown = Gauge(
            "tradepulse_risk_daily_drawdown",
            "Current daily drawdown (percentage or notional)",
            labelnames=["env", "mode"],
            **kwargs,
        )

        self.circuit_state = Gauge(
            "tradepulse_risk_circuit_state",
            "Circuit breaker state (0=closed, 1=open, 2=half_open)",
            labelnames=["state"],
            **kwargs,
        )

        self.rejections_total = Counter(
            "tradepulse_risk_rejections_total",
            "Total number of orders rejected by risk checks",
            labelnames=["reason"],
            **kwargs,
        )

        self.circuit_trips_total = Counter(
            "tradepulse_risk_circuit_trips_total",
            "Total number of circuit breaker trips",
            labelnames=["reason"],
            **kwargs,
        )

        self.open_orders = Gauge(
            "tradepulse_risk_open_orders",
            "Current number of open orders",
            labelnames=["env"],
            **kwargs,
        )

    def record_kill_switch(self, enabled: bool, env: str = "prod") -> None:
        """Record kill switch state.

        Args:
            enabled: Whether kill switch is enabled
            env: Environment label
        """
        if not self._enabled:
            return
        self.kill_switch.labels(env=env).set(1.0 if enabled else 0.0)

    def record_gross_exposure(self, exposure: float, env: str = "prod") -> None:
        """Record current gross exposure.

        Args:
            exposure: Gross exposure amount
            env: Environment label
        """
        if not self._enabled:
            return
        self.gross_exposure.labels(env=env).set(float(exposure))

    def record_daily_drawdown(
        self, drawdown: float, mode: str = "percent", env: str = "prod"
    ) -> None:
        """Record current daily drawdown.

        Args:
            drawdown: Drawdown amount
            mode: Drawdown mode (percent or notional)
            env: Environment label
        """
        if not self._enabled:
            return
        self.daily_drawdown.labels(env=env, mode=mode).set(float(drawdown))

    def record_circuit_state(self, state: str) -> None:
        """Record circuit breaker state.

        Args:
            state: Circuit state (closed, open, half_open)
        """
        if not self._enabled:
            return

        state_map = {"closed": 0.0, "open": 1.0, "half_open": 2.0}
        value = state_map.get(state.lower(), 0.0)

        for s in ["closed", "open", "half_open"]:
            self.circuit_state.labels(state=s).set(1.0 if s == state.lower() else 0.0)

    def record_rejection(self, reason: str) -> None:
        """Record an order rejection.

        Args:
            reason: Rejection reason
        """
        if not self._enabled:
            return
        self.rejections_total.labels(reason=reason).inc()

    def record_circuit_trip(self, reason: str) -> None:
        """Record a circuit breaker trip.

        Args:
            reason: Trip reason
        """
        if not self._enabled:
            return
        self.circuit_trips_total.labels(reason=reason).inc()

    def record_open_orders(self, count: int, env: str = "prod") -> None:
        """Record current open orders count.

        Args:
            count: Number of open orders
            env: Environment label
        """
        if not self._enabled:
            return
        self.open_orders.labels(env=env).set(float(count))

    @property
    def enabled(self) -> bool:
        """Check if metrics collection is enabled."""
        return self._enabled


def get_risk_metrics(registry: Optional["CollectorRegistry"] = None) -> RiskMetrics:
    """Get or create the global risk metrics instance.

    Args:
        registry: Prometheus registry (uses default if None)

    Returns:
        RiskMetrics instance
    """
    global _GLOBAL_METRICS
    if _GLOBAL_METRICS is None:
        _GLOBAL_METRICS = RiskMetrics(registry=registry)
    return _GLOBAL_METRICS
