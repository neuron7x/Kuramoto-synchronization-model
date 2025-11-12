"""Prometheus metrics exposed by the cortex service."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

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

SIGNAL_DISTRIBUTION = Histogram(
    "cortex_signal_distribution",
    "Distribution of individual signal values",
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

REGIME_TRANSITIONS = Counter(
    "cortex_regime_transition_total",
    "Number of regime transitions",
    labelnames=("from_regime", "to_regime"),
)

ERROR_COUNT = Counter(
    "cortex_error_total",
    "Total number of errors by type",
    labelnames=("code",),
)

REQUEST_INFLIGHT = Gauge(
    "cortex_request_inflight",
    "Number of requests currently being processed",
    labelnames=("endpoint",),
)

DB_OPERATION_LATENCY = Histogram(
    "cortex_db_operation_latency_seconds",
    "Latency of database operations",
    labelnames=("operation",),
)

__all__ = [
    "REQUEST_LATENCY",
    "SIGNAL_STRENGTH",
    "SIGNAL_DISTRIBUTION",
    "RISK_SCORE",
    "REGIME_UPDATES",
    "REGIME_TRANSITIONS",
    "ERROR_COUNT",
    "REQUEST_INFLIGHT",
    "DB_OPERATION_LATENCY",
]
