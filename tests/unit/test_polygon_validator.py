from __future__ import annotations

import math

from scripts.polygon_validator import PolygonValidator


def _make_bar(high: float, low: float, close: float, volume: float) -> dict[str, float]:
    return {"h": high, "l": low, "c": close, "v": volume}


def test_extract_metrics_handles_sparse_series() -> None:
    validator = PolygonValidator(api_key=None)
    validator.data = [
        _make_bar(100.0, 99.5, 99.8, 1.0e5),
        _make_bar(99.9, 99.4, 99.6, 1.05e5),
        _make_bar(99.7, 99.2, 99.4, 1.02e5),
    ]

    latencies, coherencies = validator.extract_metrics()

    assert len(latencies) == len(coherencies) == 2
    assert all(latency >= 0.0 for latency in latencies)
    assert all(0.0 <= coh <= 1.0 for coh in coherencies)


def test_run_ga_benchmark_yields_numeric_samples() -> None:
    validator = PolygonValidator(api_key=None)
    validator.data = [
        _make_bar(100.0, 99.5, 99.8, 1.0e5),
        _make_bar(99.9, 99.4, 99.6, 1.01e5),
        _make_bar(99.8, 99.3, 99.5, 0.98e5),
        _make_bar(99.6, 99.1, 99.4, 0.99e5),
    ]

    samples = validator.run_ga_benchmark(num_trials=5)

    assert len(samples) == 5
    assert all(math.isfinite(value) and value >= 0.0 for value in samples)
