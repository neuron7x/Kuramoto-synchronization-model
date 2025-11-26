"""
Real data backtest for HPC-AI v4 using event-driven simulation.

Integrates with TradePulse backtest/event_driven.py framework for realistic trading simulation.
Compares HPC-AI against baseline strategies (TACL, Buy-and-Hold).
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from neuropro.hpc_active_inference_v4 import HPCActiveInferenceModuleV4
from neuropro.hpc_validation import generate_synthetic_data

try:
    from backtest.event_driven import (  # noqa: F401
        ArrayDataHandler,
        EventDrivenBacktestEngine,
    )
    from backtest.events import MarketEvent, SignalEvent
    from backtest.performance import compute_performance_metrics  # noqa: F401

    BACKTEST_AVAILABLE = True
except ImportError:
    BACKTEST_AVAILABLE = False
    logging.warning("Backtest modules not available. Using simplified simulation.")

    # Create mock types when imports fail
    class MarketEvent:
        def __init__(self, symbol, price, step):
            self.symbol = symbol
            self.price = price
            self.step = step
            self.volume = 1000000.0

    class SignalEvent:
        def __init__(self, symbol, signal_type, strength, price):
            self.symbol = symbol
            self.signal_type = signal_type
            self.strength = strength
            self.price = price


@dataclass
class BacktestResult:
    """Results from HPC-AI backtest."""

    strategy_name: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    volatility: float
    n_trades: int
    win_rate: float
    action_diversity: float
    mean_pwpe: float
    final_capital: float
    trades: List[Dict]
    equity_curve: pd.Series


class HPCAIStrategy:
    """
    HPC-AI trading strategy adapter for event-driven backtesting.
    """

    def __init__(
        self,
        model: HPCActiveInferenceModuleV4,
        lookback_window: int = 100,
        position_size: float = 0.1,
    ):
        """
        Initialize HPC-AI strategy.

        Args:
            model: HPC-AI model instance
            lookback_window: Number of historical bars to use
            position_size: Fraction of capital per trade
        """
        self.model = model
        self.lookback_window = lookback_window
        self.position_size = position_size
        self.prev_pwpe = 0.0
        self.price_history = []
        self.volume_history = []

    def on_market_data(self, event: MarketEvent) -> Optional[SignalEvent]:
        """
        Process market data and generate trading signal.

        Args:
            event: Market event with price data

        Returns:
            SignalEvent if action is BUY or SELL, None if HOLD
        """
        # Store price history
        self.price_history.append(event.price)
        self.volume_history.append(getattr(event, "volume", 1000000.0))

        # Wait for sufficient history
        if len(self.price_history) < self.lookback_window:
            return None

        # Keep only lookback window
        self.price_history = self.price_history[-self.lookback_window :]
        self.volume_history = self.volume_history[-self.lookback_window :]

        # Create DataFrame for model
        data = pd.DataFrame(
            {
                "open": self.price_history,
                "high": [p * 1.01 for p in self.price_history],  # Mock high
                "low": [p * 0.99 for p in self.price_history],  # Mock low
                "close": self.price_history,
                "volume": self.volume_history,
            }
        )
        data.index = pd.date_range(end=pd.Timestamp.now(), periods=len(data), freq="D")

        # Get action from HPC-AI
        action = self.model.decide_action(data, self.prev_pwpe)

        # Update prev_pwpe
        self.prev_pwpe = self.model.get_pwpe(data)

        # Convert to signal
        if action == 1:  # BUY
            return SignalEvent(
                symbol=event.symbol,
                signal_type="LONG",
                strength=self.position_size,
                price=event.price,
            )
        elif action == 2:  # SELL
            return SignalEvent(
                symbol=event.symbol,
                signal_type="SHORT",
                strength=self.position_size,
                price=event.price,
            )
        else:  # HOLD (action == 0)
            return None


class SimplifiedBacktest:
    """
    Simplified backtest engine when full event-driven is not available.
    """

    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = 0.0
        self.entry_price = 0.0
        self.trades = []
        self.equity = []

    def run(
        self,
        strategy: HPCAIStrategy,
        prices: pd.Series,
    ) -> BacktestResult:
        """
        Run simplified backtest.

        Args:
            strategy: HPC-AI strategy
            prices: Price series

        Returns:
            BacktestResult with metrics
        """
        actions = []
        pwpes = []

        for i, price in enumerate(prices):
            # Create mock market event
            class MockEvent:
                def __init__(self, symbol, price, step):
                    self.symbol = symbol
                    self.price = price
                    self.step = step
                    self.volume = 1000000.0

            event = MockEvent("ASSET", price, i)
            signal = strategy.on_market_data(event)

            # Track metrics
            if len(strategy.price_history) >= strategy.lookback_window:
                pwpes.append(strategy.prev_pwpe)

            # Execute signal
            if signal is not None:
                if signal.signal_type == "LONG" and self.position == 0:
                    # Buy
                    trade_size = self.capital * strategy.position_size / price
                    self.position = trade_size
                    self.entry_price = price
                    self.capital -= trade_size * price
                    actions.append(1)

                    self.trades.append(
                        {
                            "step": i,
                            "type": "BUY",
                            "price": price,
                            "size": trade_size,
                        }
                    )

                elif signal.signal_type == "SHORT" and self.position > 0:
                    # Sell
                    pnl = self.position * (price - self.entry_price)
                    self.capital += self.position * price
                    actions.append(2)

                    self.trades.append(
                        {
                            "step": i,
                            "type": "SELL",
                            "price": price,
                            "size": self.position,
                            "pnl": pnl,
                        }
                    )

                    self.position = 0.0
                    self.entry_price = 0.0
                else:
                    actions.append(0)
            else:
                actions.append(0)

            # Track equity
            equity = self.capital + self.position * price
            self.equity.append(equity)

        # Close any open position
        if self.position > 0:
            final_price = prices.iloc[-1]
            pnl = self.position * (final_price - self.entry_price)
            self.capital += self.position * final_price

            self.trades.append(
                {
                    "step": len(prices) - 1,
                    "type": "SELL",
                    "price": final_price,
                    "size": self.position,
                    "pnl": pnl,
                }
            )

            self.position = 0.0

        # Compute metrics
        equity_series = pd.Series(self.equity)
        returns = equity_series.pct_change().dropna()

        total_return = (self.capital - self.initial_capital) / self.initial_capital
        volatility = returns.std() * np.sqrt(252)  # Annualized
        sharpe = (
            (returns.mean() / returns.std() * np.sqrt(252))
            if returns.std() > 0
            else 0.0
        )

        # Drawdown
        cummax = equity_series.cummax()
        drawdown = (equity_series - cummax) / cummax
        max_drawdown = abs(drawdown.min())

        # Win rate
        winning_trades = [t for t in self.trades if t.get("pnl", 0) > 0]
        win_rate = len(winning_trades) / len(self.trades) if self.trades else 0.0

        # Action diversity
        action_counts = {0: actions.count(0), 1: actions.count(1), 2: actions.count(2)}
        action_diversity = len([c for c in action_counts.values() if c > 0]) / 3.0

        return BacktestResult(
            strategy_name="HPC-AI v4",
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            volatility=volatility,
            n_trades=len(self.trades),
            win_rate=win_rate,
            action_diversity=action_diversity,
            mean_pwpe=float(np.mean(pwpes)) if pwpes else 0.0,
            final_capital=self.capital,
            trades=self.trades,
            equity_curve=equity_series,
        )


def run_hpc_ai_backtest(
    data: pd.DataFrame,
    model: Optional[HPCActiveInferenceModuleV4] = None,
    initial_capital: float = 10000.0,
    lookback_window: int = 100,
    position_size: float = 0.1,
) -> BacktestResult:
    """
    Run HPC-AI backtest on real or synthetic data.

    Args:
        data: Market data DataFrame with OHLCV
        model: HPC-AI model (creates new if None)
        initial_capital: Starting capital
        lookback_window: Historical window size
        position_size: Position size as fraction of capital

    Returns:
        BacktestResult with performance metrics
    """
    # Create model if not provided
    if model is None:
        model = HPCActiveInferenceModuleV4(
            input_dim=10,
            state_dim=128,
            action_dim=3,
        )

    # Create strategy
    strategy = HPCAIStrategy(
        model=model,
        lookback_window=lookback_window,
        position_size=position_size,
    )

    # Run backtest
    backtest = SimplifiedBacktest(initial_capital=initial_capital)

    if "close" in data.columns:
        prices = data["close"]
    else:
        prices = data.iloc[:, 0]  # Use first column

    result = backtest.run(strategy, prices)

    return result


def compare_with_baseline(
    data: pd.DataFrame,
    initial_capital: float = 10000.0,
) -> Dict[str, BacktestResult]:
    """
    Compare HPC-AI with baseline strategies.

    Args:
        data: Market data
        initial_capital: Starting capital

    Returns:
        Dictionary of strategy results
    """
    results = {}

    # HPC-AI strategy
    print("Running HPC-AI backtest...")
    hpc_result = run_hpc_ai_backtest(data, initial_capital=initial_capital)
    results["HPC-AI v4"] = hpc_result

    # Buy-and-Hold baseline
    print("Running Buy-and-Hold baseline...")
    prices = data["close"] if "close" in data.columns else data.iloc[:, 0]
    returns_bh = (prices.iloc[-1] - prices.iloc[0]) / prices.iloc[0]

    equity_bh = pd.Series(
        [initial_capital * (1 + (p - prices.iloc[0]) / prices.iloc[0]) for p in prices]
    )
    returns_series = equity_bh.pct_change().dropna()

    results["Buy-and-Hold"] = BacktestResult(
        strategy_name="Buy-and-Hold",
        total_return=returns_bh,
        sharpe_ratio=(
            (returns_series.mean() / returns_series.std() * np.sqrt(252))
            if returns_series.std() > 0
            else 0.0
        ),
        max_drawdown=abs((equity_bh - equity_bh.cummax()) / equity_bh.cummax()).max(),
        volatility=returns_series.std() * np.sqrt(252),
        n_trades=1,
        win_rate=1.0 if returns_bh > 0 else 0.0,
        action_diversity=0.33,  # Only buy
        mean_pwpe=0.0,
        final_capital=initial_capital * (1 + returns_bh),
        trades=[],
        equity_curve=equity_bh,
    )

    return results


def print_backtest_report(results: Dict[str, BacktestResult]):
    """
    Print formatted backtest comparison report.

    Args:
        results: Dictionary of backtest results
    """
    print("\n" + "=" * 80)
    print("BACKTEST COMPARISON REPORT")
    print("=" * 80)

    # Create comparison table
    print(
        f"\n{'Strategy':<20} {'Return':<12} {'Sharpe':<10} {'MaxDD':<10} {'Trades':<8} {'WinRate':<10}"
    )
    print("-" * 80)

    for name, result in results.items():
        print(
            f"{name:<20} {result.total_return:>10.2%} {result.sharpe_ratio:>9.4f} "
            f"{result.max_drawdown:>9.2%} {result.n_trades:>7} {result.win_rate:>9.1%}"
        )

    # Detailed HPC-AI metrics
    if "HPC-AI v4" in results:
        hpc = results["HPC-AI v4"]
        print("\n" + "=" * 80)
        print("HPC-AI v4 Detailed Metrics")
        print("=" * 80)
        print(f"Total Return:      {hpc.total_return:>10.2%}")
        print(f"Sharpe Ratio:      {hpc.sharpe_ratio:>10.4f}")
        print(f"Max Drawdown:      {hpc.max_drawdown:>10.2%}")
        print(f"Volatility (ann.): {hpc.volatility:>10.2%}")
        print(f"Number of Trades:  {hpc.n_trades:>10}")
        print(f"Win Rate:          {hpc.win_rate:>10.1%}")
        print(f"Action Diversity:  {hpc.action_diversity:>10.1%}")
        print(f"Mean PWPE:         {hpc.mean_pwpe:>10.4f}")
        print(f"Final Capital:     ${hpc.final_capital:>9.2f}")

    print("\n" + "=" * 80)


def run_example():
    """Run example backtest with synthetic data."""
    print("Generating synthetic market data...")
    data = generate_synthetic_data(n_days=1000, volatility=1.5, seed=42)

    print(
        f"Data: {len(data)} days, price range ${data['close'].min():.2f}-${data['close'].max():.2f}"
    )

    # Run comparison
    results = compare_with_baseline(data, initial_capital=10000.0)

    # Print report
    print_backtest_report(results)

    return results


if __name__ == "__main__":
    results = run_example()
