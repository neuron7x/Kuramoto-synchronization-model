# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from analytics.environment_parity import (
    EnvironmentParityChecker,
    EnvironmentParityConfig,
    EnvironmentParityError,
    MetricTolerance,
    StrategyRunSnapshot,
    compute_code_digest,
    compute_parameters_digest,
)
from backtest.performance import PerformanceReport


def _make_snapshot(
    environment: str,
    *,
    metrics: dict[str, float] | None = None,
    code_digest: str = "digest",
    parameters_digest: str = "params",
    metadata: dict[str, object] | None = None,
) -> StrategyRunSnapshot:
    base_metrics = {"pnl": 100.0, "sharpe_ratio": 1.25}
    if metrics:
        base_metrics.update(metrics)
    base_metadata = {"data_digest": "seed", "config_hash": "cfg"}
    if metadata:
        base_metadata.update(metadata)
    return StrategyRunSnapshot(
        environment=environment,
        strategy="alpha",
        metrics=base_metrics,
        timestamp=datetime(2024, 1, 1, 0, 0, 0),
        code_digest=code_digest,
        parameters_digest=parameters_digest,
        metadata=base_metadata,
    )


def test_snapshot_from_performance_report_includes_defined_metrics() -> None:
    report = PerformanceReport(sharpe_ratio=1.8, max_drawdown=-0.05)
    snapshot = StrategyRunSnapshot.from_performance_report(
        "BackTest",
        "alpha",
        report,
        extra_metrics={"pnl": 12.3},
    )
    assert snapshot.environment == "backtest"
    assert snapshot.metrics["sharpe_ratio"] == pytest.approx(1.8)
    assert snapshot.metrics["max_drawdown"] == pytest.approx(-0.05)
    assert snapshot.metrics["pnl"] == pytest.approx(12.3)
    assert "sortino_ratio" not in snapshot.metrics


def test_compute_code_digest_stable_for_callable_and_file() -> None:
    def sample_strategy(x: float) -> float:
        return x * 2

    digest_callable = compute_code_digest(sample_strategy)
    assert digest_callable == compute_code_digest(sample_strategy)

    with NamedTemporaryFile("w", delete=False) as handle:
        path = Path(handle.name)
        handle.write("def tmp_strategy(x):\n    return x + 1\n")

    try:
        digest_file = compute_code_digest(path)
        assert len(digest_file) == 64
    finally:
        path.unlink(missing_ok=True)


def test_compute_parameters_digest_order_invariant() -> None:
    params_a = {"lookback": 20, "threshold": 1.5}
    params_b = {"threshold": 1.5, "lookback": 20}
    digest_a = compute_parameters_digest(params_a)
    digest_b = compute_parameters_digest(params_b)
    assert digest_a == digest_b
    params_c = {"lookback": 21, "threshold": 1.5}
    assert compute_parameters_digest(params_c) != digest_a


def test_environment_parity_passes_within_tolerance() -> None:
    backtest = _make_snapshot("backtest")
    paper = _make_snapshot("paper", metrics={"pnl": 100.6, "sharpe_ratio": 1.26})
    live = _make_snapshot("live", metrics={"pnl": 99.8, "sharpe_ratio": 1.24})

    config = EnvironmentParityConfig(
        metric_tolerances={
            "pnl": MetricTolerance(relative=0.01, absolute=1.5),
            "sharpe_ratio": MetricTolerance(relative=0.02),
        },
    )

    report = EnvironmentParityChecker().evaluate([backtest, paper, live], config)
    assert report.status == "pass"
    assert report.ok
    assert not report.metric_deviations


def test_environment_parity_detects_metric_deviation() -> None:
    backtest = _make_snapshot("backtest")
    paper = _make_snapshot("paper", metrics={"pnl": 100.3})
    live = _make_snapshot("live", metrics={"pnl": 120.0})

    config = EnvironmentParityConfig(
        metric_tolerances={"pnl": MetricTolerance(relative=0.01, absolute=1.0)},
        required_metrics=("pnl",),
    )

    report = EnvironmentParityChecker().evaluate([backtest, paper, live], config)
    assert report.status == "fail"
    assert report.metric_deviations
    assert any(
        deviation.metric == "pnl" and deviation.comparison_environment == "live"
        for deviation in report.metric_deviations
    )
    with pytest.raises(EnvironmentParityError):
        report.raise_for_failure()


def test_environment_parity_detects_code_mismatch() -> None:
    backtest = _make_snapshot("backtest", code_digest="digest-a")
    paper = _make_snapshot("paper", code_digest="digest-a")
    live = _make_snapshot("live", code_digest="digest-b")

    config = EnvironmentParityConfig(
        metric_tolerances={"pnl": MetricTolerance(relative=0.05)},
        required_metrics=("pnl",),
    )

    report = EnvironmentParityChecker().evaluate([backtest, paper, live], config)
    assert report.status == "fail"
    assert len({value for value in report.code_digests.values() if value}) == 2
    with pytest.raises(EnvironmentParityError):
        report.raise_for_failure()


def test_environment_parity_detects_metadata_drift() -> None:
    backtest = _make_snapshot("backtest")
    paper = _make_snapshot("paper")
    live = _make_snapshot("live", metadata={"data_digest": "seed-live"})

    config = EnvironmentParityConfig(
        metric_tolerances={"pnl": MetricTolerance(relative=0.05)},
        required_metrics=("pnl",),
    )

    report = EnvironmentParityChecker().evaluate([backtest, paper, live], config)
    assert report.status == "fail"
    assert "data_digest" in report.metadata_drift


def test_environment_parity_warning_when_missing_metrics_allowed() -> None:
    backtest = _make_snapshot("backtest")
    paper = _make_snapshot("paper", metrics={"pnl": 100.0, "sharpe_ratio": None})
    live = _make_snapshot("live", metrics={"pnl": 99.5})

    config = EnvironmentParityConfig(
        metric_tolerances={"pnl": MetricTolerance(relative=0.05)},
        required_metrics=("pnl", "sharpe_ratio"),
        allow_missing_metrics=True,
    )

    report = EnvironmentParityChecker().evaluate([backtest, paper, live], config)
    assert report.status == "warning"
    assert report.missing_metrics
    report.raise_for_failure()  # Should not raise on warning
