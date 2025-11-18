from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from backtest.performance import (
    PerformanceReport,
    compute_performance_metrics,
    export_performance_report,
)


def test_compute_performance_metrics_basic() -> None:
    equity_curve = np.array([100.0, 102.0, 101.0, 105.0], dtype=float)
    pnl = equity_curve - np.concatenate(([100.0], equity_curve[:-1]))
    position_changes = np.array([0.5, -0.2, 0.3], dtype=float)

    report = compute_performance_metrics(
        equity_curve=equity_curve,
        pnl=pnl,
        position_changes=position_changes,
        initial_capital=100.0,
        max_drawdown=-4.0,
        periods_per_year=4,
    )

    assert math.isfinite(report.sharpe_ratio)
    assert report.probabilistic_sharpe_ratio is not None
    assert report.sharpe_p_value is not None
    assert report.certainty_equivalent is not None
    assert report.max_drawdown == -4.0
    assert pytest.approx(report.turnover, rel=1e-9) == float(np.sum(np.abs(position_changes)))
    assert pytest.approx(report.hit_ratio, rel=1e-9) == 2.0 / 3.0
    assert report.expected_shortfall is not None


def test_compute_performance_metrics_matches_manual_values() -> None:
    equity_curve = np.array([100.0, 105.0, 95.0, 110.0, 108.0], dtype=float)
    pnl = equity_curve - np.concatenate(([100.0], equity_curve[:-1]))
    position_changes = np.array([0.4, -0.6, 0.5, -0.2], dtype=float)
    benchmark = np.array([0.0, 0.025, -0.015, 0.02, -0.005], dtype=float)

    report = compute_performance_metrics(
        equity_curve=equity_curve,
        pnl=pnl,
        position_changes=position_changes,
        initial_capital=100.0,
        periods_per_year=4,
        benchmark_returns=benchmark,
    )

    assert report.sharpe_ratio == pytest.approx(0.4037231085, rel=1e-9)
    assert report.sortino_ratio == pytest.approx(0.6935584313, rel=1e-9)
    assert report.cagr == pytest.approx(0.06350369806, rel=1e-9)
    assert report.max_drawdown == pytest.approx(-10.0, rel=1e-9)
    assert report.expected_shortfall == pytest.approx(-0.09523809523, rel=1e-9)
    assert report.turnover == pytest.approx(1.7, rel=1e-9)
    assert report.hit_ratio == pytest.approx(0.5, rel=1e-9)
    assert report.beta == pytest.approx(4.74347925149, rel=1e-9)
    assert report.alpha == pytest.approx(-0.01928972629, rel=1e-9)
    assert report.tracking_error == pytest.approx(0.07950867954, rel=1e-9)
    assert report.information_ratio == pytest.approx(0.3495207005, rel=1e-9)
    assert report.probabilistic_sharpe_ratio == pytest.approx(0.6621069372, rel=1e-9)
    assert report.sharpe_p_value == pytest.approx(0.67510846551, rel=1e-9)
    assert report.certainty_equivalent == pytest.approx(0.05933283515, rel=1e-9)


def test_export_performance_report(tmp_path: Path) -> None:
    report = PerformanceReport(
        sharpe_ratio=1.25,
        sortino_ratio=None,
        cagr=0.12,
        max_drawdown=-0.08,
        expected_shortfall=-0.04,
        turnover=2.5,
        hit_ratio=0.55,
    )

    path = export_performance_report("My Strategy!", report, directory=tmp_path)
    assert path.parent == tmp_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["strategy"] == "My Strategy!"
    assert pytest.approx(payload["performance"]["sharpe_ratio"], rel=1e-9) == 1.25
    assert payload["performance"]["sortino_ratio"] is None
    assert "probabilistic_sharpe_ratio" in payload["performance"]
    assert "sharpe_p_value" in payload["performance"]
    assert "certainty_equivalent" in payload["performance"]


def test_factor_statistics() -> None:
    equity_curve = np.array([100.0, 110.0, 104.5], dtype=float)
    pnl = equity_curve - np.concatenate(([100.0], equity_curve[:-1]))
    benchmark = np.array([0.05, -0.02], dtype=float)

    report = compute_performance_metrics(
        equity_curve=equity_curve,
        pnl=pnl,
        position_changes=None,
        initial_capital=100.0,
        periods_per_year=2,
        benchmark_returns=benchmark,
    )

    assert report.beta is not None
    assert report.beta == pytest.approx(2.142857, rel=1e-6)
    assert report.alpha is not None
    assert report.alpha == pytest.approx(-0.0142857, rel=1e-5)
    assert report.tracking_error is not None
    assert report.tracking_error == pytest.approx(0.0565685, rel=1e-6)
    assert report.information_ratio is not None
    assert report.information_ratio == pytest.approx(0.25, rel=1e-6)
    assert report.probabilistic_sharpe_ratio is not None
    assert report.sharpe_p_value is not None
