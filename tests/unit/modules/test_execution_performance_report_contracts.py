# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Defect-sensitive contracts for execution / performance / report modules.

Targets: execution_analyzer, performance_tracker, backtest_report_generator.
Pins empty-input reports, slippage/PnL sign conventions, the impossible-drawdown
guarantee on monotone-up equity, explicit division-by-zero handling, deterministic
report schema + content hash, and a valid JSON round-trip.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from modules.backtest_report_generator import (
    BacktestReport,
    BacktestReportGenerator,
    ReportFormat,
    Trade,
)
from modules.execution_analyzer import (
    ExecutionAnalyzer,
    ExecutionRecord,
    ExecutionSide,
)
from modules.performance_tracker import PerformanceTracker


# --------------------------------------------------------------------------- #
# execution_analyzer
# --------------------------------------------------------------------------- #
def _record(side: ExecutionSide, expected: float, executed: float) -> ExecutionRecord:
    return ExecutionRecord(
        execution_id="e1", order_id="o1", symbol="AAPL", side=side, quantity=10.0,
        expected_price=expected, executed_price=executed,
        order_created_at=datetime(2022, 1, 3, 10, 0, 0),
        execution_time=datetime(2022, 1, 3, 10, 0, 0, 500_000),
    )


def test_empty_batch_returns_explicit_empty_report() -> None:
    assert ExecutionAnalyzer().analyze_batch([]) == {"error": "No executions to analyze"}


def test_slippage_sign_is_pinned_by_side() -> None:
    analyzer = ExecutionAnalyzer()
    # BUY filled ABOVE the expected price is adverse (positive bps).
    buy = analyzer.analyze_execution(_record(ExecutionSide.BUY, 100.0, 101.0))
    assert buy.slippage.direction == "adverse"
    assert buy.slippage.slippage_bps > 0.0
    # SELL filled BELOW the expected price is adverse.
    sell = analyzer.analyze_execution(_record(ExecutionSide.SELL, 100.0, 99.0))
    assert sell.slippage.direction == "adverse"
    assert sell.slippage.slippage_bps > 0.0
    # BUY filled BELOW expected is favorable.
    good = analyzer.analyze_execution(_record(ExecutionSide.BUY, 100.0, 99.0))
    assert good.slippage.direction == "favorable"


def test_execution_rejects_negative_market_data_latency() -> None:
    analyzer = ExecutionAnalyzer()
    record = _record(ExecutionSide.BUY, 100.0, 100.5)
    bad_state = {"market_data_latency_ms": -1.0}
    with pytest.raises(ValueError, match=">= 0"):
        analyzer.analyze_execution(record, market_state=bad_state)


# --------------------------------------------------------------------------- #
# performance_tracker
# --------------------------------------------------------------------------- #
def test_insufficient_history_yields_default_metrics() -> None:
    metrics = PerformanceTracker().get_metrics()
    assert metrics.max_drawdown == 0.0
    assert metrics.win_rate == 0.0
    assert metrics.total_return == 0.0


def test_monotone_up_equity_has_zero_drawdown() -> None:
    tracker = PerformanceTracker(initial_capital=100_000.0)
    for equity in (100_000.0, 101_000.0, 102_000.0, 103_500.0, 105_000.0):
        tracker.update_equity(equity=equity)
    metrics = tracker.get_metrics()
    # Drawdown is defined <= 0 of the running peak; on a monotone-up curve it is 0.
    assert metrics.max_drawdown == 0.0
    assert metrics.current_drawdown == 0.0
    assert metrics.total_return > 0.0


def test_pnl_sign_is_pinned_and_win_rate_uses_raw_counts() -> None:
    tracker = PerformanceTracker(initial_capital=100_000.0)
    tracker.record_trade("A", "sell", 1.0, 100.0, pnl=50.0)
    tracker.record_trade("A", "sell", 1.0, 100.0, pnl=-20.0)
    tracker.record_trade("A", "sell", 1.0, 100.0, pnl=30.0)
    for equity in (100_000.0, 100_500.0):
        tracker.update_equity(equity=equity)
    metrics = tracker.get_metrics()
    # 2 wins / 3 trades; profit_factor = 80 / 20 = 4.0.
    assert metrics.win_rate == pytest.approx(2.0 / 3.0)
    assert metrics.profit_factor == pytest.approx(4.0)


def test_no_trades_yields_zero_win_rate_not_division_error() -> None:
    tracker = PerformanceTracker(initial_capital=100_000.0)
    for equity in (100_000.0, 101_000.0):
        tracker.update_equity(equity=equity)
    assert tracker.get_metrics().win_rate == 0.0


# --------------------------------------------------------------------------- #
# backtest_report_generator
# --------------------------------------------------------------------------- #
def _trade(pnl: float) -> Trade:
    return Trade(
        symbol="A", entry_date=datetime(2022, 1, 3), exit_date=datetime(2022, 1, 4),
        entry_price=100.0, exit_price=100.0 + pnl, quantity=1.0, side="long",
        pnl=pnl, pnl_percent=pnl / 100.0, duration=timedelta(days=1),
    )


def test_empty_trades_yield_zeroed_statistics() -> None:
    stats = BacktestReportGenerator()._calculate_trade_statistics([])
    assert stats.total_trades == 0
    assert stats.winning_trades == 0
    assert stats.win_rate == 0.0


def test_trade_statistics_pin_pnl_extremes() -> None:
    stats = BacktestReportGenerator()._calculate_trade_statistics(
        [_trade(10.0), _trade(-10.0), _trade(5.0)]
    )
    assert stats.winning_trades == 2
    assert stats.losing_trades == 1
    assert stats.largest_win == 10.0
    assert stats.largest_loss == -10.0  # most-negative, not abs
    assert stats.win_rate == pytest.approx(2.0 / 3.0)


def test_short_return_series_yields_default_performance() -> None:
    perf = BacktestReportGenerator()._calculate_performance_metrics(pd.Series([0.01]))
    assert perf.total_return == 0.0
    assert perf.sharpe_ratio == 0.0


def _report(seed: int = 3) -> BacktestReport:
    idx = pd.date_range("2022-01-03", periods=90, freq="B")
    rng = np.random.default_rng(seed)
    returns = pd.Series(rng.normal(0.001, 0.01, 90), index=idx)
    return BacktestReportGenerator().generate_report(returns, strategy_name="S")


def test_report_schema_and_content_hash_are_deterministic() -> None:
    a = _report()
    b = _report()
    # Same declared schema (field set) every time.
    assert set(asdict(a).keys()) == set(asdict(b).keys())
    # Same content hash over the numeric payload (excluding wall-clock timestamps).
    assert _content_hash(a) == _content_hash(b)


def _content_hash(report: BacktestReport) -> str:
    payload = asdict(report)
    payload.pop("generated_at", None)
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def test_report_json_round_trip_is_valid() -> None:
    text = BacktestReportGenerator().format_report(_report(), ReportFormat.JSON)
    decoded = json.loads(text)  # must be valid JSON
    assert "performance" in decoded
    assert "drawdown" in decoded
    assert "trades" in decoded


def test_generate_report_on_empty_returns_fails_before_emit() -> None:
    with pytest.raises((IndexError, ValueError)):
        BacktestReportGenerator().generate_report(pd.Series([], dtype=float))
