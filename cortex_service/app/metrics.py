"""Prometheus metrics exposed by the cortex service."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

REQUEST_LATENCY = Histogram(
    "cognition_request_latency_seconds",
    "Latency of cognition API requests",
    labelnames=("endpoint", "method", "status"),
)

REQUEST_COUNT = Counter(
    "cognition_requests_total",
    "Total cognition API requests",
    labelnames=("endpoint", "method", "status"),
)

SIGNAL_STRENGTH = Histogram(
    "cognition_signal_strength",
    "Distribution of cognition signal amplitudes",
    buckets=(-1.0, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1.0),
)

RISK_SCORE = Histogram(
    "cognition_risk_score",
    "Distribution of computed cognition risk scores",
    buckets=(-1.0, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1.0),
)

VALENCE_GAUGE = Gauge(
    "cognition_valence_gauge",
    "Current global valence level",
)

COHERENCE_GAUGE = Gauge(
    "cognition_coherence_last",
    "Latest Kuramoto-style coherence measurement",
)

REGIME_UPDATES = Counter(
    "cognition_regime_updates_total",
    "Number of market regime updates performed",
    labelnames=("polarity",),
)

__all__ = [
    "COHERENCE_GAUGE",
    "REGIME_UPDATES",
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "RISK_SCORE",
    "SIGNAL_STRENGTH",
    "VALENCE_GAUGE",
]
