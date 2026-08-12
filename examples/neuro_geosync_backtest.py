# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import numpy as np
import pandas as pd

from backtest.event_driven import EventDrivenBacktestEngine
from core.utils.determinism import DEFAULT_SEED
from strategies.neuro_geosync import NeuroGeoSyncStrategy


def to_bars(prices: np.ndarray) -> pd.DataFrame:
    n = prices.size
    idx = pd.date_range("2024-01-01", periods=n, freq="1min")
    # simple synthetic volume with fixed seed for reproducibility
    rng = np.random.default_rng(seed=DEFAULT_SEED)
    volume = np.exp(rng.normal(9.0, 0.4, n))
    return pd.DataFrame({"close": prices, "volume": volume}, index=idx)


if __name__ == "__main__":
    rng = np.random.default_rng(DEFAULT_SEED)
    prices = 100 + np.cumsum(rng.normal(0, 1.0, 2000))
    bars = to_bars(prices)

    strat = NeuroGeoSyncStrategy()
    actions = strat.generate_signals(bars).to_numpy()

    # Wrap in a callable to match the backtest example signature
    def strategy_fn(series: np.ndarray) -> np.ndarray:
        # Use the precomputed actions truncated to current length
        # In real pipelines, recompute with available history at each step.
        return actions[: series.size]

    engine = EventDrivenBacktestEngine()
    result = engine.run(
        prices,
        strategy_fn,
        initial_capital=100_000,
        strategy_name="neuro_geosync_demo",
    )

    print("Sharpe:", getattr(result.performance, "sharpe_ratio", None))
    print("PnL:", getattr(result, "pnl", None))
    print("Max Drawdown:", getattr(result, "max_dd", None))
