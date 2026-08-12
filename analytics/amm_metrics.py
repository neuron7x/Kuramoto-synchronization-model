# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Prometheus metrics instrumentation for Adaptive Market Mind (AMM).

This module provides production-grade observability for the AMM prediction system
through Prometheus metrics. It tracks pulse intensity, precision, adaptive parameters,
and high-burst events in real-time for monitoring and alerting.

Key Components:
    timed_update: Context manager for measuring update latency
    publish_metrics: Export AMM state to Prometheus gauges and counters

Metrics Exposed:
    - amm_pulse: Current pulse intensity (gauge)
    - amm_precision: Current precision value (gauge)
    - amm_gain: Adaptive gain parameter k (gauge)
    - amm_threshold: Adaptive threshold parameter theta (gauge)
    - amm_bursts_total: Count of high-pulse burst events (counter)
    - amm_update_seconds: Update operation latency histogram

Labels include symbol and timeframe (tf) for multi-instrument monitoring.

The metrics enable production operators to:
    - Detect anomalous pulse patterns
    - Monitor adaptive parameter drift
    - Alert on burst frequency changes
    - Track performance across instruments

Example:
    >>> with timed_update("BTCUSD", "1h"):
    ...     result = amm.update(return_t, R_t, kappa_t)
    >>> publish_metrics("BTCUSD", "1h", result, amm.gain, amm.threshold)
"""

from __future__ import annotations

import time
from contextlib import contextmanager

from prometheus_client import Counter, Gauge, Histogram

_g_pulse = Gauge("amm_pulse", "AMM pulse intensity", ["symbol", "tf"])
_g_prec = Gauge("amm_precision", "AMM precision", ["symbol", "tf"])
_g_gain = Gauge("amm_gain", "AMM adaptive gain k", ["symbol", "tf"])
_g_theta = Gauge("amm_threshold", "AMM adaptive threshold theta", ["symbol", "tf"])
_c_burst = Counter("amm_bursts_total", "AMM high-pulse bursts", ["symbol", "tf"])
_h_update = Histogram("amm_update_seconds", "AMM update latency seconds", ["symbol", "tf"])


@contextmanager
def timed_update(symbol: str, tf: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        _h_update.labels(symbol, tf).observe(time.perf_counter() - start)


def publish_metrics(
    symbol: str, tf: str, out: dict, k: float, theta: float, q_hi: float | None = None
) -> None:
    _g_pulse.labels(symbol, tf).set(out["amm_pulse"])
    _g_prec.labels(symbol, tf).set(out["amm_precision"])
    _g_gain.labels(symbol, tf).set(k)
    _g_theta.labels(symbol, tf).set(theta)
    if q_hi is not None and out["amm_pulse"] >= q_hi:
        _c_burst.labels(symbol, tf).inc()
