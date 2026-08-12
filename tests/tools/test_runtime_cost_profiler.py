from __future__ import annotations

from metrics.performance_profiler import profile_validation_cycle


def _baseline() -> None:
    sum(range(200))


def _validation() -> None:
    sum(i * i for i in range(250))


def test_runtime_cost_profiler_reports_metrics() -> None:
    result = profile_validation_cycle(_validation, _baseline, runs=10)
    assert result.mean_ms >= 0
    assert result.variance_pct >= 0
    assert result.peak_memory_kib >= 0
