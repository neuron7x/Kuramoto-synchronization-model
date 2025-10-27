"""Prometheus metrics exposed by the cortex service."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

REQUEST_LATENCY = Histogram(
    "cortex_request_latency_seconds",
    "Latency of cortex API requests",
    labelnames=("endpoint", "method", "status"),
)

SIGNAL_STRENGTH = Histogram(
    "cortex_signal_strength",
    "Distribution of ensemble signal strengths",
    buckets=(-1.0, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1.0),
)

RISK_SCORE = Histogram(
    "cortex_risk_score",
    "Distribution of computed risk scores",
    buckets=(0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0),
)

REGIME_UPDATES = Counter(
    "cortex_regime_updates_total",
    "Number of market regime updates performed",
    labelnames=("regime",),
)

__all__ = [
    "REQUEST_LATENCY",
    "SIGNAL_STRENGTH",
    "RISK_SCORE",
    "REGIME_UPDATES",
]
