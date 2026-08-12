# mypy: disable-error-code="attr-defined,operator,index,arg-type,call-overload,assignment"
"""Tests for Prometheus metrics."""

from __future__ import annotations

import time

from coherence_bridge.metrics import (
    GAMMA,
    ORDER_PARAMETER_R,
    RISK_SCALAR,
    record_signal,
)


def test_record_signal_updates_all_gauges() -> None:
    sig = {
        "instrument": "TEST_INST",
        "gamma": 0.95,
        "order_parameter_R": 0.72,
        "risk_scalar": 0.95,
        "regime": "METASTABLE",
        "timestamp_ns": time.time_ns(),
    }
    record_signal(sig)

    assert GAMMA.labels(instrument="TEST_INST")._value.get() == 0.95
    assert ORDER_PARAMETER_R.labels(instrument="TEST_INST")._value.get() == 0.72
    assert RISK_SCALAR.labels(instrument="TEST_INST")._value.get() == 0.95


def test_metrics_endpoint_in_http_server() -> None:
    """Verify /metrics route is registered."""
    from coherence_bridge.http_server import app

    routes = {r.path for r in app.routes}
    assert "/metrics" in routes
