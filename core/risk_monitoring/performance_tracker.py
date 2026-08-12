# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Performance Tracking for Risk Monitoring.

This module provides comprehensive performance tracking with key metrics:
- Sharpe ratio
- Maximum drawdown
- Volatility-adjusted returns
- Sortino ratio
- Information ratio
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "PerformanceTracker",
    "PerformanceMetrics",
    "PerformanceReport",
]

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PerformanceMetrics:
    """Key performance metrics snapshot.

    Attributes:
        total_return: Total return since inception.
        total_return_pct: Total return as percentage.
        annualized_return: Annualized return.
        volatility: Annualized volatility (standard deviation).
        sharpe_ratio: Annualized Sharpe ratio.
        sortino_ratio: Annualized Sortino ratio.
        max_drawdown: Maximum drawdown (as fraction).
        max_drawdown_pct: Maximum drawdown as percentage.
        current_drawdown: Current drawdown from peak.
        calmar_ratio: Calmar ratio (annualized return / max drawdown).
        winning_periods: Number of positive return periods.
        losing_periods: Number of negative return periods.
        win_rate: Percentage of winning periods.
        avg_win: Average gain on winning periods.
        avg_loss: Average loss on losing periods.
        profit_factor: Ratio of gross profits to gross losses.
        risk_adjusted_return: Return divided by volatility.
        timestamp: When metrics were calculated.
    """

    total_return: float = 0.0
    total_return_pct: float = 0.0
    annualized_return: float = 0.0
    volatility: float = 0.0
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    current_drawdown: float = 0.0
    calmar_ratio: float | None = None
    winning_periods: int = 0
    losing_periods: int = 0
    win_rate: float | None = None
    avg_win: float | None = None
    avg_loss: float | None = None
    profit_factor: float | None = None
    risk_adjusted_return: float | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "total_return": self._clean(self.total_return),
            "total_return_pct": self._clean(self.total_return_pct),
            "annualized_return": self._clean(self.annualized_return),
            "volatility": self._clean(self.volatility),
            "sharpe_ratio": self._clean(self.sharpe_ratio),
            "sortino_ratio": self._clean(self.sortino_ratio),
            "max_drawdown": self._clean(self.max_drawdown),
            "max_drawdown_pct": self._clean(self.max_drawdown_pct),
            "current_drawdown": self._clean(self.current_drawdown),
            "calmar_ratio": self._clean(self.calmar_ratio),
            "winning_periods": self.winning_periods,
            "losing_periods": self.losing_periods,
            "win_rate": self._clean(self.win_rate),
            "avg_win": self._clean(self.avg_win),
            "avg_loss": self._clean(self.avg_loss),
            "profit_factor": self._clean(self.profit_factor),
            "risk_adjusted_return": self._clean(self.risk_adjusted_return),
            "timestamp": self.timestamp.isoformat(),
        }

    @staticmethod
    def _clean(value: float | None) -> float | None:
        if value is None:
            return None
        if not math.isfinite(value):
            return None
        return float(value)

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            "=" * 50,
            "PERFORMANCE METRICS",
            "=" * 50,
            f"Generated: {self.timestamp.isoformat()}",
            "",
            "--- RETURNS ---",
            f"Total Return: {self.total_return_pct:.2f}%",
            f"Annualized Return: {self.annualized_return:.2f}%",
            "",
            "--- RISK ---",
            f"Volatility: {self.volatility:.2%}",
            f"Max Drawdown: {self.max_drawdown_pct:.2f}%",
            f"Current Drawdown: {self.current_drawdown:.2%}",
            "",
            "--- RISK-ADJUSTED ---",
        ]

        if self.sharpe_ratio is not None:
            lines.append(f"Sharpe Ratio: {self.sharpe_ratio:.3f}")
        if self.sortino_ratio is not None:
            lines.append(f"Sortino Ratio: {self.sortino_ratio:.3f}")
        if self.calmar_ratio is not None:
            lines.append(f"Calmar Ratio: {self.calmar_ratio:.3f}")

        lines.extend(
            [
                "",
                "--- TRADE STATISTICS ---",
                f"Win Rate: {self.win_rate:.2%}" if self.win_rate else "Win Rate: N/A",
            ]
        )

        if self.profit_factor is not None:
            lines.append(f"Profit Factor: {self.profit_factor:.3f}")

        lines.append("=" * 50)
        return "\n".join(lines)


@dataclass(slots=True)
class PerformanceReport:
    """Detailed performance report for optimization.

    Attributes:
        metrics: Current performance metrics.
        equity_curve: Historical equity values.
        returns: Period returns.
        drawdown_series: Drawdown over time.
        rolling_sharpe: Rolling Sharpe ratio series.
        recommendations: Performance improvement recommendations.
    """

    metrics: PerformanceMetrics
    equity_curve: NDArray[np.float64] | None = None
    returns: NDArray[np.float64] | None = None
    drawdown_series: NDArray[np.float64] | None = None
    rolling_sharpe: NDArray[np.float64] | None = None
    recommendations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "metrics": self.metrics.to_dict(),
            "equity_curve_length": len(self.equity_curve) if self.equity_curve is not None else 0,
            "returns_length": len(self.returns) if self.returns is not None else 0,
            "recommendations": list(self.recommendations),
        }


@dataclass(slots=True)
class PerformanceTrackerConfig:
    """Configuration for performance tracker.

    Attributes:
        initial_capital: Starting capital.
        periods_per_year: Number of trading periods per year (default 252 for US
            equity markets which have approximately 252 trading days per year).
        risk_free_rate: Annual risk-free rate.
        rolling_window: Window size for rolling calculations.
        benchmark_returns: Optional benchmark returns for comparison.
    """

    initial_capital: float = 100_000.0
    periods_per_year: int = 252  # US equity trading days per year
    risk_free_rate: float = 0.0
    rolling_window: int = 20
    benchmark_returns: NDArray[np.float64] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "initial_capital": self.initial_capital,
            "periods_per_year": self.periods_per_year,
            "risk_free_rate": self.risk_free_rate,
            "rolling_window": self.rolling_window,
            "has_benchmark": self.benchmark_returns is not None,
        }


class PerformanceTracker:
    """Track and analyze trading performance.

    Provides real-time performance metrics and detailed reports
    for continuous optimization of trading strategies.

    Example:
        >>> tracker = PerformanceTracker(initial_capital=100_000)
        >>> tracker.update_equity(102_000)
        >>> tracker.update_equity(101_500)
        >>> metrics = tracker.get_metrics()
        >>> print(f"Sharpe: {metrics.sharpe_ratio:.2f}")
    """

    def __init__(
        self,
        config: PerformanceTrackerConfig | None = None,
        *,
        time_source: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize the performance tracker.

        Args:
            config: Tracker configuration.
            time_source: Optional time source for testing.
        """
        self._config = config or PerformanceTrackerConfig()
        self._time = time_source or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()

        # Equity tracking
        self._initial_capital = self._config.initial_capital
        self._equity_history: deque[float] = deque(maxlen=10000)
        self._equity_history.append(self._initial_capital)
        self._peak_equity = self._initial_capital
        self._current_equity = self._initial_capital

        # Returns tracking
        self._returns: deque[float] = deque(maxlen=10000)

        # Timestamp tracking
        self._start_time = self._time()
        self._last_update = self._start_time

        LOGGER.info(
            "Performance tracker initialized",
            extra={"config": self._config.to_dict()},
        )

    @property
    def config(self) -> PerformanceTrackerConfig:
        """Get current configuration."""
        return self._config

    def update_equity(self, equity: float) -> PerformanceMetrics:
        """Update with new equity value.

        Args:
            equity: Current portfolio equity.

        Returns:
            Updated performance metrics.
        """
        with self._lock:
            if not math.isfinite(equity) or equity < 0:
                raise ValueError("Equity must be a non-negative finite number")

            # Calculate return
            if self._current_equity > 0:
                period_return = (equity - self._current_equity) / self._current_equity
                self._returns.append(period_return)

            # Update tracking
            self._current_equity = equity
            self._equity_history.append(equity)
            self._peak_equity = max(self._peak_equity, equity)
            self._last_update = self._time()

            return self.get_metrics()

    def record_return(self, period_return: float) -> PerformanceMetrics:
        """Record a period return directly.

        Args:
            period_return: Return for the period (e.g., 0.01 for 1%).

        Returns:
            Updated performance metrics.
        """
        with self._lock:
            if not math.isfinite(period_return):
                raise ValueError("Return must be a finite number")

            self._returns.append(period_return)

            # Update equity from return
            self._current_equity *= 1 + period_return
            self._equity_history.append(self._current_equity)
            self._peak_equity = max(self._peak_equity, self._current_equity)
            self._last_update = self._time()

            return self.get_metrics()

    def get_metrics(self) -> PerformanceMetrics:
        """Calculate current performance metrics.

        Returns:
            Current performance metrics.
        """
        with self._lock:
            returns_array = np.array(list(self._returns)) if self._returns else np.array([])
            equity_array = np.array(list(self._equity_history))

            # Total return
            total_return = self._current_equity - self._initial_capital
            total_return_pct = (
                (total_return / self._initial_capital * 100) if self._initial_capital > 0 else 0.0
            )

            # Annualized metrics
            annualized_return = self._calculate_annualized_return(returns_array)
            volatility = self._calculate_volatility(returns_array)

            # Sharpe and Sortino
            sharpe_ratio = self._calculate_sharpe_ratio(returns_array)
            sortino_ratio = self._calculate_sortino_ratio(returns_array)

            # Drawdown
            max_drawdown, max_drawdown_pct = self._calculate_max_drawdown(equity_array)
            current_drawdown = self._calculate_current_drawdown()

            # Calmar ratio
            calmar_ratio = None
            if max_drawdown > 0 and annualized_return != 0:
                calmar_ratio = annualized_return / (max_drawdown_pct / 100)

            # Trade statistics
            winning, losing, win_rate, avg_win, avg_loss, profit_factor = (
                self._calculate_trade_stats(returns_array)
            )

            # Risk-adjusted return
            risk_adjusted = None
            if volatility > 0:
                risk_adjusted = total_return_pct / (volatility * 100)

            return PerformanceMetrics(
                total_return=total_return,
                total_return_pct=total_return_pct,
                annualized_return=annualized_return * 100,  # As percentage
                volatility=volatility,
                sharpe_ratio=sharpe_ratio,
                sortino_ratio=sortino_ratio,
                max_drawdown=max_drawdown,
                max_drawdown_pct=max_drawdown_pct,
                current_drawdown=current_drawdown,
                calmar_ratio=calmar_ratio,
                winning_periods=winning,
                losing_periods=losing,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                profit_factor=profit_factor,
                risk_adjusted_return=risk_adjusted,
                timestamp=self._time(),
            )

    def generate_report(self) -> PerformanceReport:
        """Generate detailed performance report.

        Returns:
            Comprehensive performance report.
        """
        with self._lock:
            metrics = self.get_metrics()

            # Get arrays
            returns_array = np.array(list(self._returns)) if self._returns else None
            equity_array = np.array(list(self._equity_history)) if self._equity_history else None

            # Calculate drawdown series
            drawdown_series = None
            if equity_array is not None and len(equity_array) > 0:
                peaks = np.maximum.accumulate(equity_array)
                drawdown_series = (peaks - equity_array) / np.maximum(peaks, 1e-10)

            # Calculate rolling Sharpe
            rolling_sharpe = None
            if returns_array is not None and len(returns_array) >= self._config.rolling_window:
                rolling_sharpe = self._calculate_rolling_sharpe(returns_array)

            # Generate recommendations
            recommendations = self._generate_recommendations(metrics)

            return PerformanceReport(
                metrics=metrics,
                equity_curve=equity_array,
                returns=returns_array,
                drawdown_series=drawdown_series,
                rolling_sharpe=rolling_sharpe,
                recommendations=tuple(recommendations),
            )

    def reset(self, initial_capital: float | None = None) -> None:
        """Reset the tracker.

        Args:
            initial_capital: New starting capital (optional).
        """
        with self._lock:
            if initial_capital is not None:
                self._initial_capital = initial_capital
                self._config = PerformanceTrackerConfig(
                    initial_capital=initial_capital,
                    periods_per_year=self._config.periods_per_year,
                    risk_free_rate=self._config.risk_free_rate,
                    rolling_window=self._config.rolling_window,
                )

            self._equity_history.clear()
            self._equity_history.append(self._initial_capital)
            self._returns.clear()
            self._peak_equity = self._initial_capital
            self._current_equity = self._initial_capital
            self._start_time = self._time()
            self._last_update = self._start_time

            LOGGER.info("Performance tracker reset")

    def get_status(self) -> dict[str, Any]:
        """Get current tracker status.

        Returns:
            Status dictionary.
        """
        with self._lock:
            metrics = self.get_metrics()
            return {
                "initial_capital": self._initial_capital,
                "current_equity": self._current_equity,
                "peak_equity": self._peak_equity,
                "total_periods": len(self._returns),
                "start_time": self._start_time.isoformat(),
                "last_update": self._last_update.isoformat(),
                "metrics": metrics.to_dict(),
            }

    def _calculate_annualized_return(self, returns: NDArray[np.float64]) -> float:
        """Calculate annualized return from period returns."""
        if len(returns) == 0:
            return 0.0

        # Compound return
        cumulative = np.prod(1 + returns) - 1

        # Annualize based on number of periods
        n_periods = len(returns)
        if n_periods < self._config.periods_per_year:
            # If less than a year, project forward
            annualized = (1 + cumulative) ** (self._config.periods_per_year / n_periods) - 1
        else:
            # If more than a year, calculate actual annualized
            years = n_periods / self._config.periods_per_year
            annualized = (1 + cumulative) ** (1 / years) - 1

        return float(annualized)

    def _calculate_volatility(self, returns: NDArray[np.float64]) -> float:
        """Calculate annualized volatility."""
        if len(returns) < 2:
            return 0.0

        std = float(np.std(returns, ddof=1))
        annualized = std * math.sqrt(self._config.periods_per_year)
        return annualized

    def _calculate_sharpe_ratio(self, returns: NDArray[np.float64]) -> float | None:
        """Calculate annualized Sharpe ratio."""
        if len(returns) < 2:
            return None

        excess_rate = self._config.risk_free_rate / self._config.periods_per_year
        excess_returns = returns - excess_rate

        mean_excess = float(np.mean(excess_returns))
        std = float(np.std(excess_returns, ddof=1))

        if std < 1e-10:
            return None

        sharpe = (mean_excess / std) * math.sqrt(self._config.periods_per_year)
        return float(sharpe)

    def _calculate_sortino_ratio(self, returns: NDArray[np.float64]) -> float | None:
        """Calculate annualized Sortino ratio."""
        if len(returns) < 2:
            return None

        excess_rate = self._config.risk_free_rate / self._config.periods_per_year
        excess_returns = returns - excess_rate

        mean_excess = float(np.mean(excess_returns))
        downside_returns = excess_returns[excess_returns < 0]

        if len(downside_returns) < 2:
            return None

        downside_std = float(np.std(downside_returns, ddof=1))
        if downside_std < 1e-10:
            return None

        sortino = (mean_excess / downside_std) * math.sqrt(self._config.periods_per_year)
        return float(sortino)

    def _calculate_max_drawdown(self, equity: NDArray[np.float64]) -> tuple[float, float]:
        """Calculate maximum drawdown."""
        if len(equity) == 0:
            return 0.0, 0.0

        peaks = np.maximum.accumulate(equity)
        drawdowns = (peaks - equity) / np.maximum(peaks, 1e-10)
        max_dd_pct = float(np.max(drawdowns)) * 100

        # Absolute max drawdown
        max_dd_abs = float(np.max(peaks - equity))

        return max_dd_abs, max_dd_pct

    def _calculate_current_drawdown(self) -> float:
        """Calculate current drawdown from peak."""
        if self._peak_equity <= 0:
            return 0.0
        return max(0.0, (self._peak_equity - self._current_equity) / self._peak_equity)

    def _calculate_trade_stats(
        self, returns: NDArray[np.float64]
    ) -> tuple[int, int, float | None, float | None, float | None, float | None]:
        """Calculate trade statistics."""
        if len(returns) == 0:
            return 0, 0, None, None, None, None

        winning = int(np.sum(returns > 0))
        losing = int(np.sum(returns < 0))

        win_rate = winning / len(returns) if len(returns) > 0 else None

        winners = returns[returns > 0]
        losers = returns[returns < 0]

        avg_win = float(np.mean(winners)) if len(winners) > 0 else None
        avg_loss = float(np.mean(losers)) if len(losers) > 0 else None

        profit_factor = None
        if len(losers) > 0:
            gross_profit = float(np.sum(winners)) if len(winners) > 0 else 0.0
            gross_loss = abs(float(np.sum(losers)))
            if gross_loss > 1e-10:
                profit_factor = gross_profit / gross_loss

        return winning, losing, win_rate, avg_win, avg_loss, profit_factor

    def _calculate_rolling_sharpe(self, returns: NDArray[np.float64]) -> NDArray[np.float64]:
        """Calculate rolling Sharpe ratio."""
        window = self._config.rolling_window
        if len(returns) < window:
            return np.array([])

        rolling_sharpe = np.zeros(len(returns) - window + 1)
        excess_rate = self._config.risk_free_rate / self._config.periods_per_year

        for i in range(len(rolling_sharpe)):
            window_returns = returns[i : i + window] - excess_rate
            mean = np.mean(window_returns)
            std = np.std(window_returns, ddof=1)
            if std > 1e-10:
                rolling_sharpe[i] = (mean / std) * math.sqrt(self._config.periods_per_year)
            else:
                rolling_sharpe[i] = 0.0

        return rolling_sharpe

    def _generate_recommendations(self, metrics: PerformanceMetrics) -> list[str]:
        """Generate performance improvement recommendations."""
        recommendations: list[str] = []

        # Sharpe-based recommendations
        if metrics.sharpe_ratio is not None:
            if metrics.sharpe_ratio < 0:
                recommendations.append(
                    "CRITICAL: Negative Sharpe ratio indicates strategy is underperforming risk-free rate"
                )
            elif metrics.sharpe_ratio < 0.5:
                recommendations.append(
                    "LOW SHARPE: Consider improving risk-adjusted returns through better entry/exit timing"
                )
            elif metrics.sharpe_ratio > 2.0:
                recommendations.append(
                    "EXCELLENT SHARPE: Current strategy shows strong risk-adjusted performance"
                )

        # Drawdown recommendations
        if metrics.max_drawdown_pct > 20:
            recommendations.append(
                "HIGH DRAWDOWN: Consider implementing tighter stop-losses or position sizing"
            )

        # Win rate recommendations
        if metrics.win_rate is not None:
            if metrics.win_rate < 0.4 and metrics.profit_factor and metrics.profit_factor < 1.0:
                recommendations.append(
                    "LOW WIN RATE: Strategy may need improved signal quality or risk management"
                )

        # Volatility recommendations
        if metrics.volatility > 0.3:
            recommendations.append(
                "HIGH VOLATILITY: Consider reducing position sizes or improving diversification"
            )

        return recommendations
