# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Prometheus metrics for risk controls, circuit breaker, and trading modes.

This module provides instrumentation for risk compliance checks,
circuit breaker state, rejection reasons, and trading mode transitions.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry

try:
    from prometheus_client import Counter, Gauge, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


__all__ = [
    "RiskMetrics",
    "TradingModeMetrics",
    "get_risk_metrics",
    "get_trading_mode_metrics",
]


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
            "geosync_risk_kill_switch",
            "Global kill switch state (1=enabled, 0=disabled)",
            labelnames=["env"],
            **kwargs,
        )

        self.gross_exposure = Gauge(
            "geosync_risk_gross_exposure",
            "Current gross exposure in notional terms",
            labelnames=["env"],
            **kwargs,
        )

        self.daily_drawdown = Gauge(
            "geosync_risk_daily_drawdown",
            "Current daily drawdown (percentage or notional)",
            labelnames=["env", "mode"],
            **kwargs,
        )

        self.circuit_state = Gauge(
            "geosync_risk_circuit_state",
            "Circuit breaker state (0=closed, 1=open, 2=half_open)",
            labelnames=["state"],
            **kwargs,
        )

        self.rejections_total = Counter(
            "geosync_risk_rejections_total",
            "Total number of orders rejected by risk checks",
            labelnames=["reason"],
            **kwargs,
        )

        self.circuit_trips_total = Counter(
            "geosync_risk_circuit_trips_total",
            "Total number of circuit breaker trips",
            labelnames=["reason"],
            **kwargs,
        )

        self.open_orders = Gauge(
            "geosync_risk_open_orders",
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


# Trading Mode Metrics

_GLOBAL_MODE_METRICS: Optional["TradingModeMetrics"] = None


class TradingModeMetrics:
    """Metrics collector for trading mode transitions (BACKTEST/PAPER/LIVE)."""

    def __init__(self, registry: Optional["CollectorRegistry"] = None) -> None:
        """Initialize trading mode metrics.

        Args:
            registry: Prometheus registry (uses default if None)
        """
        self._registry = registry
        self._enabled = PROMETHEUS_AVAILABLE
        self._current_mode: str = "unknown"
        self._mode_start_time: float = time.time()

        if not self._enabled:
            return

        kwargs = {"registry": registry} if registry else {}

        self.trading_mode = Gauge(
            "geosync_trading_mode",
            "Current trading mode (1 when active for that mode label)",
            labelnames=["mode"],
            **kwargs,
        )

        self.mode_transitions_total = Counter(
            "geosync_trading_mode_transitions_total",
            "Total number of trading mode transitions",
            labelnames=["from_mode", "to_mode", "reason"],
            **kwargs,
        )

        self.mode_duration_seconds = Gauge(
            "geosync_trading_mode_duration_seconds",
            "Time spent in current trading mode",
            labelnames=["mode"],
            **kwargs,
        )

        self.mode_transition_latency = Histogram(
            "geosync_trading_mode_transition_latency_seconds",
            "Latency of mode transitions",
            labelnames=["from_mode", "to_mode"],
            **kwargs,
        )

    def set_mode(self, mode: str, reason: str = "initial") -> None:
        """Set the current trading mode.

        Args:
            mode: Trading mode (BACKTEST, PAPER, LIVE)
            reason: Reason for the mode (initial, manual, automated, etc.)
        """
        if not self._enabled:
            return

        mode_upper = mode.upper()
        previous_mode = self._current_mode

        # Record transition if mode changed
        if previous_mode != "unknown" and previous_mode != mode_upper:
            self.mode_transitions_total.labels(
                from_mode=previous_mode, to_mode=mode_upper, reason=reason
            ).inc()

        # Update mode duration for previous mode
        if previous_mode != "unknown":
            duration = time.time() - self._mode_start_time
            self.mode_duration_seconds.labels(mode=previous_mode).set(duration)

        # Set new mode
        self._current_mode = mode_upper
        self._mode_start_time = time.time()

        # Update mode gauge (set active mode to 1, others to 0)
        for m in ["BACKTEST", "PAPER", "LIVE"]:
            self.trading_mode.labels(mode=m).set(1.0 if m == mode_upper else 0.0)

    def record_transition_latency(self, from_mode: str, to_mode: str, latency: float) -> None:
        """Record the latency of a mode transition.

        Args:
            from_mode: Previous trading mode
            to_mode: New trading mode
            latency: Transition latency in seconds
        """
        if not self._enabled:
            return
        self.mode_transition_latency.labels(
            from_mode=from_mode.upper(), to_mode=to_mode.upper()
        ).observe(latency)

    def update_duration(self) -> None:
        """Update the duration gauge for the current mode."""
        if not self._enabled or self._current_mode == "unknown":
            return
        duration = time.time() - self._mode_start_time
        self.mode_duration_seconds.labels(mode=self._current_mode).set(duration)

    @property
    def current_mode(self) -> str:
        """Return the current trading mode."""
        return self._current_mode

    @property
    def enabled(self) -> bool:
        """Check if metrics collection is enabled."""
        return self._enabled


def get_trading_mode_metrics(
    registry: Optional["CollectorRegistry"] = None,
) -> TradingModeMetrics:
    """Get or create the global trading mode metrics instance.

    Args:
        registry: Prometheus registry (uses default if None)

    Returns:
        TradingModeMetrics instance
    """
    global _GLOBAL_MODE_METRICS
    if _GLOBAL_MODE_METRICS is None:
        _GLOBAL_MODE_METRICS = TradingModeMetrics(registry=registry)
    return _GLOBAL_MODE_METRICS
