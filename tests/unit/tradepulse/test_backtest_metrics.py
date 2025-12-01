# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for backtest_metrics module."""

from __future__ import annotations

import numpy as np
import pytest

from tradepulse.analytics.backtest_metrics import (
    BacktestReport,
    Trade,
    evaluate_backtest,
)


class TestTrade:
    """Tests for Trade dataclass."""

    def test_trade_is_closed(self) -> None:
        """Test is_closed property."""
        open_trade = Trade(
            entry_time=0,
            exit_time=None,
            entry_price=100.0,
            exit_price=None,
            quantity=1.0,
            pnl=0.0,
        )
        assert not open_trade.is_closed

        closed_trade = Trade(
            entry_time=0,
            exit_time=1,
            entry_price=100.0,
            exit_price=105.0,
            quantity=1.0,
            pnl=5.0,
        )
        assert closed_trade.is_closed

    def test_trade_is_winner(self) -> None:
        """Test is_winner property."""
        winner = Trade(
            entry_time=0,
            exit_time=1,
            entry_price=100.0,
            exit_price=105.0,
            quantity=1.0,
            pnl=5.0,
        )
        assert winner.is_winner

        loser = Trade(
            entry_time=0,
            exit_time=1,
            entry_price=100.0,
            exit_price=95.0,
            quantity=1.0,
            pnl=-5.0,
        )
        assert not loser.is_winner

    def test_trade_gross_pnl(self) -> None:
        """Test gross_pnl calculation."""
        trade = Trade(
            entry_time=0,
            exit_time=1,
            entry_price=100.0,
            exit_price=105.0,
            quantity=1.0,
            pnl=4.0,  # Net of costs
            commission=0.5,
            slippage=0.5,
        )
        assert trade.gross_pnl == pytest.approx(5.0)


class TestEvaluateBacktest:
    """Tests for evaluate_backtest function."""

    def test_basic_equity_curve_metrics(self) -> None:
        """Test basic PnL and return calculations."""
        equity = np.array([100.0, 102.0, 101.0, 105.0, 108.0])
        report = evaluate_backtest(equity_curve=equity, initial_capital=100.0)

        assert report.total_pnl == pytest.approx(8.0)
        assert report.total_return_pct == pytest.approx(8.0)
        assert report.equity_curve is not None
        assert len(report.equity_curve) == 5

    def test_drawdown_calculation(self) -> None:
        """Test max drawdown calculation."""
        # Simple case: peak at 110, trough at 95
        equity = np.array([100.0, 105.0, 110.0, 100.0, 95.0, 105.0])
        report = evaluate_backtest(equity_curve=equity, initial_capital=100.0)

        # Max drawdown should be from 110 to 95 = -15
        assert report.max_drawdown == pytest.approx(-15.0)
        # As percentage of peak (110): -15/110 * 100 = -13.64%
        assert report.max_drawdown_pct == pytest.approx(-13.636363636, rel=1e-3)

    def test_series_of_losses_drawdown(self) -> None:
        """Test drawdown with continuous losses."""
        # Continuous decline
        equity = np.array([100.0, 90.0, 80.0, 70.0, 60.0])
        report = evaluate_backtest(equity_curve=equity, initial_capital=100.0)

        # Max drawdown from 100 to 60 = -40
        assert report.max_drawdown == pytest.approx(-40.0)
        assert report.max_drawdown_pct == pytest.approx(-40.0)

    def test_sharpe_ratio_calculation(self) -> None:
        """Test Sharpe ratio calculation."""
        # Generate returns that produce a known Sharpe ratio
        np.random.seed(42)
        returns = np.array([0.01, 0.02, -0.01, 0.015, 0.005, 0.02, -0.005])
        equity = 100 * np.cumprod(1 + returns)
        equity = np.concatenate(([100.0], equity))

        report = evaluate_backtest(
            equity_curve=equity,
            initial_capital=100.0,
            periods_per_year=252,
        )

        assert report.sharpe_ratio is not None
        # Verify it's a reasonable value
        assert -5 < report.sharpe_ratio < 10

    def test_trade_statistics(self) -> None:
        """Test trade statistics calculation."""
        trades = [
            Trade(
                entry_time=0,
                exit_time=1,
                entry_price=100.0,
                exit_price=105.0,
                quantity=1.0,
                pnl=5.0,
            ),
            Trade(
                entry_time=1,
                exit_time=2,
                entry_price=105.0,
                exit_price=103.0,
                quantity=1.0,
                pnl=-2.0,
            ),
            Trade(
                entry_time=2,
                exit_time=3,
                entry_price=103.0,
                exit_price=110.0,
                quantity=1.0,
                pnl=7.0,
            ),
        ]

        report = evaluate_backtest(trade_log=trades, initial_capital=100.0)

        assert report.total_trades == 3
        assert report.winning_trades == 2
        assert report.losing_trades == 1
        assert report.hit_rate == pytest.approx(2 / 3)
        assert report.avg_trade_pnl == pytest.approx((5 - 2 + 7) / 3)
        assert report.avg_winner == pytest.approx((5 + 7) / 2)
        assert report.avg_loser == pytest.approx(-2.0)
        assert report.largest_winner == pytest.approx(7.0)
        assert report.largest_loser == pytest.approx(-2.0)

    def test_profit_factor(self) -> None:
        """Test profit factor calculation."""
        trades = [
            Trade(
                entry_time=0,
                exit_time=1,
                entry_price=100.0,
                exit_price=110.0,
                quantity=1.0,
                pnl=10.0,
            ),
            Trade(
                entry_time=1,
                exit_time=2,
                entry_price=110.0,
                exit_price=105.0,
                quantity=1.0,
                pnl=-5.0,
            ),
        ]

        report = evaluate_backtest(trade_log=trades, initial_capital=100.0)

        # Profit factor = gross profit / gross loss = 10 / 5 = 2.0
        assert report.profit_factor == pytest.approx(2.0)

    def test_consecutive_wins_losses(self) -> None:
        """Test consecutive wins/losses tracking."""
        trades = [
            Trade(
                entry_time=i,
                exit_time=i + 1,
                entry_price=100.0,
                exit_price=100.0 + pnl,
                quantity=1.0,
                pnl=pnl,
            )
            for i, pnl in enumerate([5, 3, 2, -1, -2, -3, 4, 5])
        ]

        report = evaluate_backtest(trade_log=trades, initial_capital=100.0)

        assert report.max_consecutive_wins == 3  # First 3 trades
        assert report.max_consecutive_losses == 3  # Middle 3 trades

    def test_exposure_calculation(self) -> None:
        """Test market exposure calculation."""
        positions = np.array([0, 1, 1, 0, 0, 1, 0, 0, 0, 1])
        report = evaluate_backtest(
            equity_curve=np.linspace(100, 110, 10),
            initial_capital=100.0,
            positions=positions,
        )

        # 4 out of 10 periods have non-zero positions = 40%
        assert report.exposure_pct == pytest.approx(40.0)

    def test_commission_slippage_totals(self) -> None:
        """Test commission and slippage aggregation."""
        trades = [
            Trade(
                entry_time=0,
                exit_time=1,
                entry_price=100.0,
                exit_price=105.0,
                quantity=1.0,
                pnl=4.0,
                commission=0.5,
                slippage=0.5,
            ),
            Trade(
                entry_time=1,
                exit_time=2,
                entry_price=105.0,
                exit_price=110.0,
                quantity=1.0,
                pnl=4.0,
                commission=0.75,
                slippage=0.25,
            ),
        ]

        report = evaluate_backtest(trade_log=trades, initial_capital=100.0)

        assert report.total_commission == pytest.approx(1.25)
        assert report.total_slippage == pytest.approx(0.75)

    def test_empty_equity_curve(self) -> None:
        """Test handling of empty equity curve."""
        report = evaluate_backtest(equity_curve=np.array([]), initial_capital=100.0)

        assert report.total_pnl == 0.0
        assert report.total_return_pct == 0.0
        assert report.max_drawdown == 0.0

    def test_no_trades(self) -> None:
        """Test handling when no trades are provided."""
        report = evaluate_backtest(
            equity_curve=np.array([100.0, 102.0, 104.0]),
            initial_capital=100.0,
        )

        assert report.total_trades == 0
        assert report.hit_rate is None
        assert report.profit_factor is None


class TestBacktestReportSerialization:
    """Tests for BacktestReport serialization."""

    def test_as_dict_serializable(self) -> None:
        """Test that as_dict returns JSON-serializable data."""
        import json

        equity = np.array([100.0, 105.0, 103.0, 108.0])
        report = evaluate_backtest(equity_curve=equity, initial_capital=100.0)
        report_dict = report.as_dict()

        # Should be JSON serializable
        json_str = json.dumps(report_dict)
        assert isinstance(json_str, str)

        # Should contain expected fields
        assert "total_pnl" in report_dict
        assert "max_drawdown" in report_dict
        assert "sharpe_ratio" in report_dict
        assert "generated_at" in report_dict

    def test_summary_format(self) -> None:
        """Test that summary returns formatted string."""
        equity = np.array([100.0, 105.0, 103.0, 108.0])
        report = evaluate_backtest(equity_curve=equity, initial_capital=100.0)
        summary = report.summary()

        assert "BACKTEST REPORT" in summary
        assert "Total PnL" in summary
        assert "Max Drawdown" in summary


class TestDrawdownInfo:
    """Tests for DrawdownInfo calculations."""

    def test_drawdown_info_populated(self) -> None:
        """Test that drawdown info is correctly populated."""
        equity = np.array([100.0, 110.0, 105.0, 95.0, 100.0, 112.0])
        report = evaluate_backtest(equity_curve=equity, initial_capital=100.0)

        assert report.drawdown_info is not None
        dd_info = report.drawdown_info

        # Peak is at index 1 (110)
        assert dd_info.peak_value == pytest.approx(110.0)
        # Trough is at index 3 (95)
        assert dd_info.trough_value == pytest.approx(95.0)
        # Max drawdown is -15
        assert dd_info.max_drawdown == pytest.approx(-15.0)

    def test_drawdown_recovery_tracking(self) -> None:
        """Test drawdown recovery is tracked."""
        equity = np.array([100.0, 110.0, 100.0, 115.0])  # Recovers past peak
        report = evaluate_backtest(equity_curve=equity, initial_capital=100.0)

        dd_info = report.drawdown_info
        assert dd_info is not None
        # Should have recovered at index 3 (115 > 110)
        assert dd_info.end_idx == 3


class TestEdgeCases:
    """Tests for edge cases and mathematical correctness."""

    def test_single_period(self) -> None:
        """Test with single period equity curve."""
        equity = np.array([100.0])
        report = evaluate_backtest(equity_curve=equity, initial_capital=100.0)

        assert report.total_pnl == pytest.approx(0.0)
        assert report.sharpe_ratio is None  # Can't compute with single value

    def test_zero_initial_capital(self) -> None:
        """Test handling of zero initial capital."""
        equity = np.array([0.0, 10.0, 20.0])
        report = evaluate_backtest(equity_curve=equity, initial_capital=0.0)

        # Return should be infinite or handled gracefully
        assert report.total_pnl == pytest.approx(20.0)

    def test_all_winning_trades(self) -> None:
        """Test with all winning trades."""
        trades = [
            Trade(
                entry_time=i,
                exit_time=i + 1,
                entry_price=100.0,
                exit_price=105.0,
                quantity=1.0,
                pnl=5.0,
            )
            for i in range(5)
        ]

        report = evaluate_backtest(trade_log=trades, initial_capital=100.0)

        assert report.hit_rate == pytest.approx(1.0)
        assert report.losing_trades == 0
        assert report.avg_loser is None  # No losers
        assert report.profit_factor is None  # No losses to divide by

    def test_all_losing_trades(self) -> None:
        """Test with all losing trades."""
        trades = [
            Trade(
                entry_time=i,
                exit_time=i + 1,
                entry_price=100.0,
                exit_price=95.0,
                quantity=1.0,
                pnl=-5.0,
            )
            for i in range(5)
        ]

        report = evaluate_backtest(trade_log=trades, initial_capital=100.0)

        assert report.hit_rate == pytest.approx(0.0)
        assert report.winning_trades == 0
        assert report.avg_winner is None  # No winners
        assert report.profit_factor == pytest.approx(0.0)  # Zero profit

    def test_nan_handling(self) -> None:
        """Test that NaN values in equity don't crash."""
        equity = np.array([100.0, 105.0, np.nan, 108.0])

        # Should not raise
        report = evaluate_backtest(equity_curve=equity, initial_capital=100.0)
        assert report is not None

    def test_infinite_values_cleaned(self) -> None:
        """Test that infinite values are cleaned in output."""
        report = BacktestReport(
            total_pnl=float("inf"),
            total_return_pct=float("-inf"),
            max_drawdown=-10.0,
            max_drawdown_pct=-10.0,
            sharpe_ratio=float("nan"),
        )

        report_dict = report.as_dict()
        assert report_dict["total_pnl"] is None
        assert report_dict["total_return_pct"] is None
        assert report_dict["sharpe_ratio"] is None
