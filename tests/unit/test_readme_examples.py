# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validate code examples from README.md to ensure they remain functional."""

import numpy as np
import pandas as pd


def test_readme_composite_engine_example() -> None:
    """Validate the main README example with GeoSyncCompositeEngine."""
    from core.indicators.kuramoto_ricci_composite import GeoSyncCompositeEngine

    # Build a synthetic intraday data set
    np.random.seed(42)
    index = pd.date_range("2024-01-01", periods=720, freq="5min")
    price = 100 + np.cumsum(np.random.normal(0, 0.6, index.size))
    volume = np.random.lognormal(mean=9.5, sigma=0.35, size=index.size)
    bars = pd.DataFrame({"close": price, "volume": volume}, index=index)

    # Analyze the market regime with the Kuramoto–Ricci composite engine
    engine = GeoSyncCompositeEngine()
    snapshot = engine.analyze_market(bars)

    # Validate output structure
    assert hasattr(snapshot, "phase")
    assert hasattr(snapshot, "confidence")
    assert hasattr(snapshot, "entry_signal")
    assert snapshot.phase.value in [
        "accumulation",
        "markup",
        "distribution",
        "markdown",
        "transition",
    ]
    assert 0.0 <= snapshot.confidence <= 1.0
    assert -1.0 <= snapshot.entry_signal <= 1.0


def test_readme_kuramoto_strategy_example() -> None:
    """Validate the backtest example from README."""
    from backtest.event_driven import EventDrivenBacktestEngine
    from core.indicators import KuramotoIndicator

    # Generate a synthetic closing price series
    rng = np.random.default_rng(seed=42)
    prices = 100 + np.cumsum(rng.normal(0, 1, 500))
    indicator = KuramotoIndicator(window=80, coupling=0.9)

    def kuramoto_signal(series: np.ndarray) -> np.ndarray:
        order = indicator.compute(series)
        signal = np.where(order > 0.75, 1.0, np.where(order < 0.25, -1.0, 0.0))
        warmup = min(indicator.window, signal.size)
        signal[:warmup] = 0.0
        return signal

    engine = EventDrivenBacktestEngine()
    result = engine.run(
        prices,
        kuramoto_signal,
        initial_capital=100_000,
        strategy_name="kuramoto_demo",
    )

    # Validate result structure
    assert hasattr(result, "pnl")
    assert hasattr(result, "max_dd")
    assert hasattr(result, "trades")
    assert isinstance(result.pnl, (int, float))
    assert isinstance(result.max_dd, (int, float))
    assert isinstance(result.trades, int)


def test_readme_streaming_buffer_example() -> None:
    """Validate the streaming buffer example from docstring."""
    from core.data.streaming import RollingBuffer

    buffer = RollingBuffer(size=100)
    buffer.push(42.5)
    values = buffer.values()

    assert len(values) == 1
    assert values[0] == 42.5
    assert buffer.is_full() is False


def test_readme_volume_metrics_example() -> None:
    """Validate volume profile examples from docstring."""
    from core.metrics.volume_profile import cumulative_volume_delta, imbalance

    buys = np.array([100, 150, 200])
    sells = np.array([80, 120, 180])

    cvd = cumulative_volume_delta(buys, sells)
    imb = imbalance(buys, sells)

    assert cvd.shape == buys.shape
    assert np.array_equal(cvd, np.array([20.0, 50.0, 70.0]))
    assert isinstance(imb, float)
    assert -1.0 <= imb <= 1.0
