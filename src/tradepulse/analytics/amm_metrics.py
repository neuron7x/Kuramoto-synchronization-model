from __future__ import annotations

import time
from contextlib import contextmanager

from prometheus_client import Counter, Gauge, Histogram

_g_pulse = Gauge("amm_pulse", "AMM pulse intensity", ["symbol", "tf"])
_g_prec = Gauge("amm_precision", "AMM precision", ["symbol", "tf"])
_g_gain = Gauge("amm_gain", "AMM adaptive gain k", ["symbol", "tf"])
_g_theta = Gauge("amm_threshold", "AMM adaptive threshold theta", ["symbol", "tf"])
_c_burst = Counter("amm_bursts_total", "AMM high-pulse bursts", ["symbol", "tf"])
_h_update = Histogram(
    "amm_update_seconds", "AMM update latency seconds", ["symbol", "tf"]
)


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
