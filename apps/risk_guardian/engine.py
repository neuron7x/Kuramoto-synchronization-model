# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Risk Guardian core engine — simulates trading with and without risk controls."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from .config import RiskGuardianConfig, SimulationResult

__all__ = ["RiskGuardian", "RiskGuardianConfig", "SimulationResult"]

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class TradeSignal:
    """A trade signal to be evaluated by Risk Guardian."""

    timestamp: datetime
    price: float
    signal: float  # -1 to 1: short to long
    symbol: str = "ASSET"


@dataclass(slots=True)
class RiskState:
    """Internal state for risk tracking."""

    equity: float
    peak_equity: float
    daily_pnl: float
    position: float
    is_halted: bool = False
    is_safe_mode: bool = False
    last_reset_date: datetime | None = None


class RiskGuardian:
    """Risk Guardian — automated risk control for any trading strategy.

    This is the main product interface. It takes a configuration and provides
    methods to:
    1. Simulate historical trades with risk controls
    2. Compare baseline (no controls) vs protected (with controls) performance
    3. Generate money-denominated reports

    Example:
        >>> config = RiskGuardianConfig(
        ...     daily_loss_limit_pct=5.0,
        ...     max_drawdown_pct=10.0,
        ... )
        >>> guardian = RiskGuardian(config)
        >>> result = guardian.simulate_from_prices(prices, signal_fn)
        >>> print(result.summary())
    """

    def __init__(self, config: RiskGuardianConfig | None = None) -> None:
        """Initialize the Risk Guardian.

        Args:
            config: Risk configuration. Uses defaults if not provided.
        """
        self._config = config or RiskGuardianConfig()

    @property
    def config(self) -> RiskGuardianConfig:
        """Get the current configuration."""
        return self._config

    def simulate_from_prices(
        self,
        prices: NDArray[np.float64] | pd.Series,
        signal_fn: Callable[[NDArray[np.float64]], NDArray[np.float64]],
        *,
        timestamps: pd.DatetimeIndex | None = None,
    ) -> SimulationResult:
        """Simulate risk-controlled trading from price series and signal function.

        Args:
            prices: Array of prices.
            signal_fn: Function that takes prices and returns signals (-1 to 1).
            timestamps: Optional timestamps for the price data.

        Returns:
            SimulationResult with comparison metrics.
        """
        if isinstance(prices, pd.Series):
            if timestamps is None and isinstance(prices.index, pd.DatetimeIndex):
                timestamps = prices.index
            prices = prices.to_numpy(dtype=float)

        prices = np.asarray(prices, dtype=float)
        signals = np.asarray(signal_fn(prices), dtype=float)
        signals = np.clip(signals, -1.0, 1.0)

        if timestamps is None:
            timestamps = pd.date_range(
                start="2024-01-01", periods=len(prices), freq="h"
            )

        return self._run_simulation(prices, signals, timestamps)

    def simulate_from_dataframe(
        self,
        df: pd.DataFrame,
        price_col: str = "close",
        signal_col: str | None = None,
        signal_fn: Callable[[NDArray[np.float64]], NDArray[np.float64]] | None = None,
        timestamp_col: str | None = None,
    ) -> SimulationResult:
        """Simulate from a DataFrame with price and signal columns.

        Args:
            df: DataFrame with price data.
            price_col: Name of the price column.
            signal_col: Name of the signal column (if pre-computed).
            signal_fn: Signal generation function (if not using signal_col).
            timestamp_col: Name of the timestamp column.

        Returns:
            SimulationResult with comparison metrics.
        """
        if price_col not in df.columns:
            raise ValueError(f"Price column '{price_col}' not found in DataFrame")

        prices = df[price_col].to_numpy(dtype=float)

        if signal_col is not None and signal_col in df.columns:
            signals = df[signal_col].to_numpy(dtype=float)
        elif signal_fn is not None:
            signals = np.asarray(signal_fn(prices), dtype=float)
        else:
            raise ValueError("Must provide either signal_col or signal_fn")

        signals = np.clip(signals, -1.0, 1.0)

        if timestamp_col is not None and timestamp_col in df.columns:
            timestamps = pd.to_datetime(df[timestamp_col])
        elif isinstance(df.index, pd.DatetimeIndex):
            timestamps = df.index
        else:
            timestamps = pd.date_range(
                start="2024-01-01", periods=len(prices), freq="h"
            )

        return self._run_simulation(prices, signals, timestamps)

    def _run_simulation(
        self,
        prices: NDArray[np.float64],
        signals: NDArray[np.float64],
        timestamps: pd.DatetimeIndex,
    ) -> SimulationResult:
        """Run both baseline and protected simulations.

        Args:
            prices: Array of prices.
            signals: Array of signals (-1 to 1).
            timestamps: Timestamps for each price.

        Returns:
            SimulationResult comparing baseline vs protected.
        """
        n = len(prices)
        if n < 2:
            raise ValueError("Need at least 2 price points for simulation")
        if len(signals) != n:
            raise ValueError("Signals must have same length as prices")

        # Calculate returns
        returns = np.diff(prices) / prices[:-1]
        returns = np.concatenate([[0.0], returns])

        # Run baseline simulation (no risk controls)
        baseline_equity, baseline_daily = self._simulate_baseline(
            prices, signals, returns, timestamps
        )

        # Run protected simulation (with risk controls)
        protected_equity, protected_daily, risk_events = self._simulate_protected(
            prices, signals, returns, timestamps
        )

        # Calculate metrics
        baseline_pnl = baseline_equity[-1] - self._config.initial_capital
        protected_pnl = protected_equity[-1] - self._config.initial_capital

        baseline_dd = self._calculate_max_drawdown(baseline_equity)
        protected_dd = self._calculate_max_drawdown(protected_equity)

        baseline_sharpe = self._calculate_sharpe(baseline_daily)
        protected_sharpe = self._calculate_sharpe(protected_daily)

        baseline_worst = min(baseline_daily) if len(baseline_daily) > 0 else 0.0
        protected_worst = min(protected_daily) if len(protected_daily) > 0 else 0.0

        # Calculate saved capital
        peak_baseline = max(baseline_equity)
        trough_baseline = min(baseline_equity)
        peak_protected = max(protected_equity)
        trough_protected = min(protected_equity)

        # Saved capital = difference in worst case losses
        baseline_max_loss = peak_baseline - trough_baseline
        protected_max_loss = peak_protected - trough_protected
        saved_capital = max(0.0, baseline_max_loss - protected_max_loss)
        saved_capital_pct = (
            (saved_capital / peak_baseline * 100) if peak_baseline > 0 else 0.0
        )

        return SimulationResult(
            baseline_pnl=baseline_pnl,
            protected_pnl=protected_pnl,
            baseline_max_drawdown=baseline_dd,
            protected_max_drawdown=protected_dd,
            saved_capital=saved_capital,
            saved_capital_pct=saved_capital_pct,
            kill_switch_activations=risk_events["kill_switch"],
            safe_mode_periods=risk_events["safe_mode"],
            blocked_trades=risk_events["blocked"],
            baseline_sharpe=baseline_sharpe,
            protected_sharpe=protected_sharpe,
            baseline_worst_day=baseline_worst,
            protected_worst_day=protected_worst,
            total_periods=n,
            config=self._config,
        )

    def _simulate_baseline(
        self,
        prices: NDArray[np.float64],
        signals: NDArray[np.float64],
        returns: NDArray[np.float64],
        timestamps: pd.DatetimeIndex,
    ) -> tuple[NDArray[np.float64], list[float]]:
        """Simulate without any risk controls.

        Returns:
            Tuple of (equity curve, daily returns list).
        """
        equity = np.zeros(len(prices))
        equity[0] = self._config.initial_capital

        position = 0.0
        daily_returns: list[float] = []
        current_day: datetime | None = None
        day_start_equity = self._config.initial_capital

        for i in range(1, len(prices)):
            # Update equity from position
            if position != 0:
                pnl = position * (prices[i] - prices[i - 1])
                equity[i] = equity[i - 1] + pnl
            else:
                equity[i] = equity[i - 1]

            # Track daily returns
            ts = timestamps[i]
            if current_day is None or ts.date() != current_day:
                if current_day is not None and day_start_equity > 0:
                    day_return = (equity[i - 1] - day_start_equity) / day_start_equity
                    daily_returns.append(day_return)
                current_day = ts.date()
                day_start_equity = equity[i - 1]

            # Update position based on signal
            target_position = (
                signals[i]
                * (equity[i] * self._config.max_position_pct / 100.0)
                / prices[i]
            )
            position = target_position

        # Final day return
        if day_start_equity > 0 and len(prices) > 0:
            final_return = (equity[-1] - day_start_equity) / day_start_equity
            daily_returns.append(final_return)

        return equity, daily_returns

    def _simulate_protected(
        self,
        prices: NDArray[np.float64],
        signals: NDArray[np.float64],
        returns: NDArray[np.float64],
        timestamps: pd.DatetimeIndex,
    ) -> tuple[NDArray[np.float64], list[float], dict[str, int]]:
        """Simulate with Risk Guardian controls.

        Returns:
            Tuple of (equity curve, daily returns, risk events dict).
        """
        equity = np.zeros(len(prices))
        equity[0] = self._config.initial_capital

        state = RiskState(
            equity=self._config.initial_capital,
            peak_equity=self._config.initial_capital,
            daily_pnl=0.0,
            position=0.0,
        )

        daily_returns: list[float] = []
        current_day: datetime | None = None
        day_start_equity = self._config.initial_capital

        risk_events = {"kill_switch": 0, "safe_mode": 0, "blocked": 0}

        for i in range(1, len(prices)):
            ts = timestamps[i]

            # Reset daily tracking at day change
            if current_day is None or ts.date() != current_day:
                if current_day is not None and day_start_equity > 0:
                    day_return = (state.equity - day_start_equity) / day_start_equity
                    daily_returns.append(day_return)

                    # Check daily loss limit
                    if day_return < -self._config.daily_loss_limit_pct / 100:
                        daily_returns[-1] = -self._config.daily_loss_limit_pct / 100

                current_day = ts.date()
                day_start_equity = state.equity
                state.daily_pnl = 0.0

                # Reset kill-switch if we're at a new day and drawdown recovered
                current_dd = self._get_drawdown(state.equity, state.peak_equity)
                if (
                    state.is_halted
                    and current_dd < self._config.safe_mode_threshold_pct / 100
                ):
                    state.is_halted = False
                    LOGGER.info("Kill-switch deactivated at %s", ts)

            # Update equity from position
            if state.position != 0:
                pnl = state.position * (prices[i] - prices[i - 1])
            else:
                pnl = 0.0

            state.equity += pnl
            state.daily_pnl += pnl
            state.peak_equity = max(state.peak_equity, state.equity)
            equity[i] = state.equity

            # Check risk limits
            current_dd = self._get_drawdown(state.equity, state.peak_equity)
            daily_loss_pct = (
                -state.daily_pnl / day_start_equity if day_start_equity > 0 else 0
            )

            # Kill-switch check
            if (
                self._config.enable_kill_switch
                and current_dd >= self._config.max_drawdown_pct / 100
            ):
                if not state.is_halted:
                    state.is_halted = True
                    risk_events["kill_switch"] += 1
                    LOGGER.warning(
                        "Kill-switch activated at %s (drawdown: %.1f%%)",
                        ts,
                        current_dd * 100,
                    )

            # Safe mode check
            _ = state.is_safe_mode  # Track prior state for logging/metrics
            if (
                self._config.enable_safe_mode
                and current_dd >= self._config.safe_mode_threshold_pct / 100
            ):
                state.is_safe_mode = True
            elif (
                current_dd < self._config.safe_mode_threshold_pct / 100 * 0.8
            ):  # Hysteresis
                state.is_safe_mode = False

            # Count periods spent in safe mode
            if state.is_safe_mode:
                risk_events["safe_mode"] += 1

            # Daily loss limit check
            if daily_loss_pct >= self._config.daily_loss_limit_pct / 100:
                state.is_halted = True

            # Determine target position
            if state.is_halted:
                target_position = 0.0
                if signals[i] != 0:
                    risk_events["blocked"] += 1
            else:
                position_multiplier = (
                    self._config.safe_mode_position_multiplier
                    if state.is_safe_mode
                    else 1.0
                )
                max_pos_value = (
                    state.equity
                    * self._config.max_position_pct
                    / 100
                    * position_multiplier
                )
                target_position = signals[i] * max_pos_value / prices[i]

            state.position = target_position

        # Final day return
        if day_start_equity > 0 and len(prices) > 0:
            final_return = (state.equity - day_start_equity) / day_start_equity
            # Cap at daily limit
            if final_return < -self._config.daily_loss_limit_pct / 100:
                final_return = -self._config.daily_loss_limit_pct / 100
            daily_returns.append(final_return)

        return equity, daily_returns, risk_events

    @staticmethod
    def _get_drawdown(equity: float, peak_equity: float) -> float:
        """Calculate current drawdown as a fraction."""
        if peak_equity <= 0:
            return 0.0
        return max(0.0, (peak_equity - equity) / peak_equity)

    @staticmethod
    def _calculate_max_drawdown(equity: NDArray[np.float64]) -> float:
        """Calculate maximum drawdown from equity curve."""
        if len(equity) == 0:
            return 0.0
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / np.maximum(peak, 1e-10)
        return float(np.max(drawdown))

    @staticmethod
    def _calculate_sharpe(
        daily_returns: list[float], periods_per_year: int = 252
    ) -> float:
        """Calculate annualized Sharpe ratio from daily returns."""
        if len(daily_returns) < 2:
            return 0.0
        returns = np.array(daily_returns)
        mean = np.mean(returns)
        std = np.std(returns, ddof=1)
        if std == 0:
            return 0.0
        return float(mean / std * np.sqrt(periods_per_year))
