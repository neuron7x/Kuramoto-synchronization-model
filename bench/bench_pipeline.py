# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Microbenchmarks for the ingest → features → signals → orders pipeline."""

from __future__ import annotations

import statistics
import time
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from backtest.execution_simulation import MatchingEngine, Order, OrderSide, OrderType
from core.agent.strategy import Strategy
from core.data.preprocess import normalize_df
from core.indicators.ricci import MeanRicciFeature

RNG = np.random.default_rng(42)
ROWS = 10_000

SYNTHETIC_DF = pd.DataFrame(
    {
        "ts": np.arange(ROWS, dtype=float) * 60.0,
        "price": 100.0 + RNG.standard_normal(ROWS).cumsum(),
        "volume": RNG.uniform(0.1, 5.0, ROWS),
    }
)

PRICE_SERIES = SYNTHETIC_DF["price"].to_numpy()
RICCI_FEATURE = MeanRicciFeature(delta=0.01)


def benchmark(name: str, func: Callable[[], None], *, iterations: int = 7) -> None:
    samples: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        samples.append(time.perf_counter() - start)
    best = min(samples)
    avg = statistics.mean(samples)
    print(f"{name:<32s} best={best * 1e3:6.2f} ms  avg={avg * 1e3:6.2f} ms")


def run_ingestion() -> None:
    normalize_df(SYNTHETIC_DF)


def run_feature_transform() -> None:
    RICCI_FEATURE.transform(PRICE_SERIES)


def run_signal_generation() -> None:
    params = {"lookback": 60, "threshold": 0.8, "risk_budget": 1.5}
    strategy = Strategy(name="mean_reversion", params=params)
    strategy.simulate_performance(PRICE_SERIES)


def run_order_submission() -> None:
    engine = MatchingEngine(latency_model=lambda order: 25)
    engine.add_passive_liquidity("BTC-USD", OrderSide.SELL, price=20_500, qty=5.0, timestamp=0)
    order = Order(
        id="bench-1",
        symbol="BTC-USD",
        side=OrderSide.BUY,
        qty=1.0,
        timestamp=0,
        order_type=OrderType.MARKET,
    )
    engine.submit_order(order)
    engine.process_until(50)


def main(iterations: int = 7) -> None:
    benches: Iterable[tuple[str, Callable[[], None]]] = (
        ("normalize_df", run_ingestion),
        ("ricci_feature", run_feature_transform),
        ("strategy_simulation", run_signal_generation),
        ("matching_engine_submit", run_order_submission),
    )
    for name, func in benches:
        benchmark(name, func, iterations=iterations)


if __name__ == "__main__":
    main()
