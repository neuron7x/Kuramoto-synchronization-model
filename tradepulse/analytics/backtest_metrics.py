# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Backtest metrics and reporting module.

This module provides comprehensive metrics for evaluating backtest results.
It computes industry-standard performance metrics and generates structured
reports suitable for strategy comparison and audit trails.

**Key Metrics**

* Total PnL and return percentages
* Maximum drawdown (absolute and percentage)
* Risk-adjusted returns (Sharpe, Sortino ratios)
* Trade statistics (hit rate, average R/R, exposure)
* Time-series analysis of equity curve

**Usage**

    >>> from tradepulse.analytics.backtest_metrics import evaluate_backtest
    >>> report = evaluate_backtest(
    ...     trade_log=trades,
    ...     equity_curve=equity,
    ...     initial_capital=100000.0,
    ... )
    >>> print(report.summary())
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

import numpy as np
from numpy.typing import NDArray


@dataclass(slots=True)
class Trade:
    """Represents a single trade in the trade log.

    Attributes:
        entry_time: Timestamp when the trade was entered
        exit_time: Timestamp when the trade was exited (None if still open)
        entry_price: Price at which the position was entered
        exit_price: Price at which the position was exited (None if still open)
        quantity: Number of units traded (positive for long, negative for short)
        pnl: Realized profit/loss from the trade
        commission: Total commission paid for entry and exit
        slippage: Total slippage cost
        side: 'long' or 'short'
    """

    entry_time: datetime | int | float
    exit_time: datetime | int | float | None
    entry_price: float
    exit_price: float | None
    quantity: float
    pnl: float
    commission: float = 0.0
    slippage: float = 0.0
    side: str = "long"

    @property
    def is_closed(self) -> bool:
        """Return True if the trade has been closed."""
        return self.exit_time is not None and self.exit_price is not None

    @property
    def is_winner(self) -> bool:
        """Return True if the trade was profitable."""
        return self.pnl > 0

    @property
    def gross_pnl(self) -> float:
        """Return PnL before commissions and slippage."""
        return self.pnl + self.commission + self.slippage


@dataclass(slots=True)
class DrawdownInfo:
    """Information about a drawdown period.

    Attributes:
        start_idx: Index where the drawdown started (peak)
        end_idx: Index where the drawdown ended (recovery)
        trough_idx: Index of the maximum drawdown point
        peak_value: Equity value at the peak
        trough_value: Equity value at the trough
        max_drawdown: Maximum drawdown value (negative)
        max_drawdown_pct: Maximum drawdown as percentage
        duration: Number of periods in the drawdown
        recovery_duration: Number of periods from trough to recovery
    """

    start_idx: int
    end_idx: int | None
    trough_idx: int
    peak_value: float
    trough_value: float
    max_drawdown: float
    max_drawdown_pct: float
    duration: int | None = None
    recovery_duration: int | None = None


@dataclass(slots=True)
class BacktestReport:
    """Comprehensive backtest evaluation report.

    Attributes:
        total_pnl: Net profit/loss after all costs
        total_return_pct: Return as percentage of initial capital
        max_drawdown: Maximum drawdown (absolute value, negative)
        max_drawdown_pct: Maximum drawdown as percentage
        sharpe_ratio: Annualized Sharpe ratio (if computable)
        sortino_ratio: Annualized Sortino ratio (if computable)
        hit_rate: Percentage of winning trades
        profit_factor: Ratio of gross profits to gross losses
        avg_trade_pnl: Average PnL per trade
        avg_winner: Average PnL of winning trades
        avg_loser: Average PnL of losing trades
        avg_risk_reward: Average risk/reward ratio
        total_trades: Total number of completed trades
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        total_commission: Total commission costs
        total_slippage: Total slippage costs
        exposure_pct: Percentage of time in the market
        largest_winner: PnL of the largest winning trade
        largest_loser: PnL of the largest losing trade (negative)
        max_consecutive_wins: Maximum consecutive winning trades
        max_consecutive_losses: Maximum consecutive losing trades
        equity_curve: The equity curve array
        drawdown_info: Information about the maximum drawdown period
        periods_per_year: Number of periods per year for annualization
        generated_at: Timestamp when the report was generated
    """

    total_pnl: float
    total_return_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    hit_rate: float | None = None
    profit_factor: float | None = None
    avg_trade_pnl: float | None = None
    avg_winner: float | None = None
    avg_loser: float | None = None
    avg_risk_reward: float | None = None
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_commission: float = 0.0
    total_slippage: float = 0.0
    exposure_pct: float | None = None
    largest_winner: float | None = None
    largest_loser: float | None = None
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    equity_curve: NDArray[np.float64] | None = None
    drawdown_info: DrawdownInfo | None = None
    periods_per_year: int = 252
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def summary(self) -> str:
        """Return a human-readable summary of the report."""
        lines = [
            "=" * 50,
            "BACKTEST REPORT",
            "=" * 50,
            f"Generated: {self.generated_at.isoformat()}",
            "",
            "--- PERFORMANCE ---",
            f"Total PnL: {self.total_pnl:,.2f}",
            f"Total Return: {self.total_return_pct:.2f}%",
            f"Max Drawdown: {self.max_drawdown:,.2f} ({self.max_drawdown_pct:.2f}%)",
            "",
            "--- RISK-ADJUSTED ---",
        ]

        if self.sharpe_ratio is not None:
            lines.append(f"Sharpe Ratio: {self.sharpe_ratio:.3f}")
        if self.sortino_ratio is not None:
            lines.append(f"Sortino Ratio: {self.sortino_ratio:.3f}")

        lines.extend(
            [
                "",
                "--- TRADE STATISTICS ---",
                f"Total Trades: {self.total_trades}",
                f"Winning Trades: {self.winning_trades}",
                f"Losing Trades: {self.losing_trades}",
            ]
        )

        if self.hit_rate is not None:
            lines.append(f"Hit Rate: {self.hit_rate:.2%}")
        if self.profit_factor is not None:
            lines.append(f"Profit Factor: {self.profit_factor:.3f}")
        if self.avg_trade_pnl is not None:
            lines.append(f"Avg Trade PnL: {self.avg_trade_pnl:,.2f}")

        lines.extend(
            [
                "",
                "--- COSTS ---",
                f"Total Commission: {self.total_commission:,.2f}",
                f"Total Slippage: {self.total_slippage:,.2f}",
                "=" * 50,
            ]
        )

        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""
        return {
            "total_pnl": self._clean(self.total_pnl),
            "total_return_pct": self._clean(self.total_return_pct),
            "max_drawdown": self._clean(self.max_drawdown),
            "max_drawdown_pct": self._clean(self.max_drawdown_pct),
            "sharpe_ratio": self._clean(self.sharpe_ratio),
            "sortino_ratio": self._clean(self.sortino_ratio),
            "hit_rate": self._clean(self.hit_rate),
            "profit_factor": self._clean(self.profit_factor),
            "avg_trade_pnl": self._clean(self.avg_trade_pnl),
            "avg_winner": self._clean(self.avg_winner),
            "avg_loser": self._clean(self.avg_loser),
            "avg_risk_reward": self._clean(self.avg_risk_reward),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_commission": self._clean(self.total_commission),
            "total_slippage": self._clean(self.total_slippage),
            "exposure_pct": self._clean(self.exposure_pct),
            "largest_winner": self._clean(self.largest_winner),
            "largest_loser": self._clean(self.largest_loser),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "periods_per_year": self.periods_per_year,
            "generated_at": self.generated_at.isoformat(),
        }

    @staticmethod
    def _clean(value: float | None) -> float | None:
        if value is None:
            return None
        if not math.isfinite(value):
            return None
        return float(value)


def _compute_drawdown(
    equity_curve: NDArray[np.float64],
) -> tuple[float, float, DrawdownInfo | None]:
    """Compute maximum drawdown and related metrics.

    Returns:
        Tuple of (max_drawdown, max_drawdown_pct, drawdown_info)
    """
    if len(equity_curve) == 0:
        return 0.0, 0.0, None

    peaks = np.maximum.accumulate(equity_curve)
    drawdowns = equity_curve - peaks
    max_dd_idx = int(np.argmin(drawdowns))
    max_dd = float(drawdowns[max_dd_idx])

    # Find the peak before the max drawdown
    peak_idx = int(np.argmax(equity_curve[: max_dd_idx + 1])) if max_dd_idx > 0 else 0
    peak_value = float(peaks[max_dd_idx])
    trough_value = float(equity_curve[max_dd_idx])

    # Calculate percentage drawdown
    if peak_value > 0:
        max_dd_pct = (max_dd / peak_value) * 100
    else:
        max_dd_pct = 0.0

    # Find recovery point (if any)
    recovery_idx: int | None = None
    remaining = equity_curve[max_dd_idx:]
    if len(remaining) > 1:
        recovery_mask = remaining >= peak_value
        if recovery_mask.any():
            recovery_idx = max_dd_idx + int(np.argmax(recovery_mask))

    duration = (recovery_idx - peak_idx) if recovery_idx is not None else None
    recovery_duration = (
        (recovery_idx - max_dd_idx) if recovery_idx is not None else None
    )

    info = DrawdownInfo(
        start_idx=peak_idx,
        end_idx=recovery_idx,
        trough_idx=max_dd_idx,
        peak_value=peak_value,
        trough_value=trough_value,
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
        duration=duration,
        recovery_duration=recovery_duration,
    )

    return max_dd, max_dd_pct, info


def _compute_sharpe_sortino(
    returns: NDArray[np.float64],
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
) -> tuple[float | None, float | None]:
    """Compute Sharpe and Sortino ratios.

    Returns:
        Tuple of (sharpe_ratio, sortino_ratio)
    """
    if len(returns) < 2:
        return None, None

    annualization = math.sqrt(periods_per_year)
    excess_rate = risk_free_rate / periods_per_year

    excess_returns = returns - excess_rate
    mean_excess = float(np.mean(excess_returns))
    volatility = float(np.std(excess_returns, ddof=1))

    sharpe_ratio: float | None = None
    if volatility > 1e-12:
        sharpe_ratio = (mean_excess / volatility) * annualization

    # Sortino ratio (downside deviation)
    sortino_ratio: float | None = None
    downside_returns = excess_returns[excess_returns < 0]
    if len(downside_returns) > 1:
        # Use sample standard deviation (ddof=1) when we have enough data
        downside_vol = float(np.std(downside_returns, ddof=1))
        if downside_vol > 1e-12:
            sortino_ratio = (mean_excess / downside_vol) * annualization
    elif len(downside_returns) == 1:
        # With only one downside return, we can't compute a meaningful deviation
        # Skip Sortino calculation in this case
        pass

    return sharpe_ratio, sortino_ratio


def _compute_trade_statistics(
    trades: Sequence[Trade],
) -> dict[str, Any]:
    """Compute statistics from a sequence of trades."""
    stats: dict[str, Any] = {
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "hit_rate": None,
        "profit_factor": None,
        "avg_trade_pnl": None,
        "avg_winner": None,
        "avg_loser": None,
        "avg_risk_reward": None,
        "total_commission": 0.0,
        "total_slippage": 0.0,
        "largest_winner": None,
        "largest_loser": None,
        "max_consecutive_wins": 0,
        "max_consecutive_losses": 0,
    }

    if not trades:
        return stats

    closed_trades = [t for t in trades if t.is_closed]
    if not closed_trades:
        return stats

    pnls = [t.pnl for t in closed_trades]
    winners = [t.pnl for t in closed_trades if t.is_winner]
    losers = [t.pnl for t in closed_trades if not t.is_winner and t.pnl < 0]

    stats["total_trades"] = len(closed_trades)
    stats["winning_trades"] = len(winners)
    stats["losing_trades"] = len(losers)
    stats["total_commission"] = sum(t.commission for t in trades)
    stats["total_slippage"] = sum(t.slippage for t in trades)

    # Hit rate
    if len(closed_trades) > 0:
        stats["hit_rate"] = len(winners) / len(closed_trades)

    # Average PnL
    stats["avg_trade_pnl"] = float(np.mean(pnls)) if pnls else None

    # Average winner/loser
    if winners:
        stats["avg_winner"] = float(np.mean(winners))
        stats["largest_winner"] = float(max(winners))
    if losers:
        stats["avg_loser"] = float(np.mean(losers))
        stats["largest_loser"] = float(min(losers))

    # Profit factor
    gross_profit = sum(winners) if winners else 0.0
    gross_loss = abs(sum(losers)) if losers else 0.0
    if gross_loss > 1e-12:
        stats["profit_factor"] = gross_profit / gross_loss

    # Average risk/reward ratio
    if stats["avg_winner"] is not None and stats["avg_loser"] is not None:
        if abs(stats["avg_loser"]) > 1e-12:
            stats["avg_risk_reward"] = stats["avg_winner"] / abs(stats["avg_loser"])

    # Consecutive wins/losses
    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0

    for trade in closed_trades:
        if trade.is_winner:
            current_wins += 1
            current_losses = 0
            max_wins = max(max_wins, current_wins)
        else:
            current_losses += 1
            current_wins = 0
            max_losses = max(max_losses, current_losses)

    stats["max_consecutive_wins"] = max_wins
    stats["max_consecutive_losses"] = max_losses

    return stats


def _compute_exposure(
    positions: NDArray[np.float64] | None,
) -> float | None:
    """Compute the percentage of time with non-zero position."""
    if positions is None or len(positions) == 0:
        return None

    non_zero = np.count_nonzero(positions)
    return (non_zero / len(positions)) * 100


def evaluate_backtest(
    trade_log: Sequence[Trade] | None = None,
    equity_curve: NDArray[np.float64] | Sequence[float] | None = None,
    *,
    initial_capital: float = 0.0,
    positions: NDArray[np.float64] | Sequence[float] | None = None,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
) -> BacktestReport:
    """Evaluate a backtest and generate a comprehensive report.

    Args:
        trade_log: Sequence of Trade objects representing completed trades.
            If None, trade statistics will be computed from the equity curve.
        equity_curve: Array of equity values over time. Required for computing
            drawdown and risk-adjusted metrics.
        initial_capital: Starting capital for the backtest. Used for computing
            return percentages.
        positions: Optional array of position sizes over time. Used for computing
            market exposure.
        periods_per_year: Number of trading periods per year for annualization.
            Default is 252 (trading days).
        risk_free_rate: Annual risk-free rate for Sharpe ratio calculation.

    Returns:
        BacktestReport with computed metrics.

    Example:
        >>> import numpy as np
        >>> equity = np.array([100, 102, 101, 105, 103, 108])
        >>> report = evaluate_backtest(equity_curve=equity, initial_capital=100)
        >>> print(f"Total Return: {report.total_return_pct:.1f}%")
        Total Return: 8.0%
    """
    # Convert equity curve to numpy array
    if equity_curve is not None:
        equity = np.asarray(equity_curve, dtype=float)
    else:
        equity = np.array([], dtype=float)

    # Compute basic PnL metrics
    if len(equity) > 0:
        final_equity = float(equity[-1])
        total_pnl = final_equity - initial_capital
        if initial_capital > 0:
            total_return_pct = (total_pnl / initial_capital) * 100
        else:
            total_return_pct = 0.0 if total_pnl == 0 else float("inf")
    else:
        total_pnl = 0.0
        total_return_pct = 0.0

    # Compute drawdown
    max_dd, max_dd_pct, dd_info = _compute_drawdown(equity)

    # Compute returns for risk metrics
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    if len(equity) > 1:
        # Compute period returns
        prev_equity = np.concatenate(([initial_capital], equity[:-1]))
        with np.errstate(divide="ignore", invalid="ignore"):
            returns = (equity - prev_equity) / prev_equity
        returns = returns[np.isfinite(returns)]
        sharpe_ratio, sortino_ratio = _compute_sharpe_sortino(
            returns, periods_per_year, risk_free_rate
        )

    # Compute trade statistics
    trade_stats = _compute_trade_statistics(trade_log or [])

    # Compute exposure
    pos_array = np.asarray(positions, dtype=float) if positions is not None else None
    exposure_pct = _compute_exposure(pos_array)

    return BacktestReport(
        total_pnl=total_pnl,
        total_return_pct=total_return_pct,
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        hit_rate=trade_stats["hit_rate"],
        profit_factor=trade_stats["profit_factor"],
        avg_trade_pnl=trade_stats["avg_trade_pnl"],
        avg_winner=trade_stats["avg_winner"],
        avg_loser=trade_stats["avg_loser"],
        avg_risk_reward=trade_stats["avg_risk_reward"],
        total_trades=trade_stats["total_trades"],
        winning_trades=trade_stats["winning_trades"],
        losing_trades=trade_stats["losing_trades"],
        total_commission=trade_stats["total_commission"],
        total_slippage=trade_stats["total_slippage"],
        exposure_pct=exposure_pct,
        largest_winner=trade_stats["largest_winner"],
        largest_loser=trade_stats["largest_loser"],
        max_consecutive_wins=trade_stats["max_consecutive_wins"],
        max_consecutive_losses=trade_stats["max_consecutive_losses"],
        equity_curve=equity if len(equity) > 0 else None,
        drawdown_info=dd_info,
        periods_per_year=periods_per_year,
    )


__all__ = [
    "BacktestReport",
    "DrawdownInfo",
    "Trade",
    "evaluate_backtest",
]
