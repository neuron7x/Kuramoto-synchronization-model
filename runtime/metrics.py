"""Prometheus instrumentation helpers."""

from __future__ import annotations

from typing import Dict

from prometheus_client import Gauge, start_http_server


_METRICS: Dict[str, Gauge] = {}


def _get_gauge(name: str) -> Gauge:
    if name not in _METRICS:
        _METRICS[name] = Gauge(name, f"TradePulse metric {name}")
    return _METRICS[name]


def init_metrics_server(port: int = 9200) -> None:
    """Start the Prometheus metrics server if not already running."""

    start_http_server(port)
    # Ensure gauges exist so acceptance test can scrape them immediately.
    for gauge_name in (
        "tradepulse_coverage",
        "tradepulse_q_enbpi",
        "tradepulse_ood_score",
        "tradepulse_lambda_cvar",
        "tradepulse_drawdown",
        "tradepulse_step_latency_ms",
        "tacl_free_energy",
        "tacl_change_denied_total",
    ):
        _get_gauge(gauge_name)


def gauge_set(name: str, value: float) -> None:
    """Set a gauge value."""

    _get_gauge(name).set(value)


__all__ = ["init_metrics_server", "gauge_set"]
