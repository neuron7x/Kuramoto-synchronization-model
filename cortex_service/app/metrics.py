"""Prometheus metrics exposed by the cortex service.

This module defines all Prometheus metrics used for observability.
Metrics are organized by category: requests, signals, risk, regime, errors, and database.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# Request metrics
REQUEST_LATENCY = Histogram(
    "cortex_request_latency_seconds",
    "Latency of cortex API requests",
    labelnames=("endpoint", "method", "status"),
)

REQUEST_INFLIGHT = Gauge(
    "cortex_requests_inflight",
    "Number of requests currently being processed",
    labelnames=("endpoint", "method"),
)

# Signal metrics
SIGNAL_STRENGTH = Histogram(
    "cortex_signal_strength",
    "Distribution of ensemble signal strengths",
    buckets=(-1.0, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1.0),
)

SIGNAL_DISTRIBUTION = Histogram(
    "cortex_signal_distribution",
    "Distribution of individual signal values",
    buckets=(-1.0, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1.0),
    labelnames=("instrument",),
)

# Risk metrics
RISK_SCORE = Histogram(
    "cortex_risk_score",
    "Distribution of computed risk scores",
    buckets=(0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0),
)

# Regime metrics
REGIME_UPDATES = Counter(
    "cortex_regime_updates_total",
    "Number of market regime updates performed",
    labelnames=("regime",),
)

REGIME_TRANSITIONS = Counter(
    "cortex_regime_transitions_total",
    "Number of regime transitions",
    labelnames=("from_regime", "to_regime"),
)

# Error metrics
ERROR_COUNT = Counter(
    "cortex_errors_total",
    "Total number of errors encountered",
    labelnames=("error_code", "endpoint"),
)

# Database metrics
DB_OPERATION_LATENCY = Histogram(
    "cortex_db_operation_latency_seconds",
    "Latency of database operations",
    labelnames=("operation",),
)

__all__ = [
    "DB_OPERATION_LATENCY",
    "ERROR_COUNT",
    "REGIME_TRANSITIONS",
    "REGIME_UPDATES",
    "REQUEST_INFLIGHT",
    "REQUEST_LATENCY",
    "RISK_SCORE",
    "SIGNAL_DISTRIBUTION",
    "SIGNAL_STRENGTH",
]
