# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Test helpers for GeoSync agent integration tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from application.system import (
    ExchangeAdapterConfig,
    GeoSyncSystem,
    GeoSyncSystemConfig,
    LiveLoopSettings,
)
from execution.connectors import BinanceConnector


def write_sample_ohlc(path: Path, *, periods: int = 128) -> None:
    """Persist a deterministic OHLCV sample to *path*."""

    index = pd.date_range("2024-01-01", periods=periods, freq="min", tz="UTC")
    base_price = 100.0
    rng = np.random.default_rng(seed=42)
    drift = rng.normal(0.0, 0.1, size=periods).cumsum()
    close = base_price + drift
    open_prices = close + rng.normal(0.0, 0.05, size=periods)
    high = np.maximum(open_prices, close) + rng.uniform(0.0, 0.1, size=periods)
    low = np.minimum(open_prices, close) - rng.uniform(0.0, 0.1, size=periods)
    volume = rng.integers(1_000, 5_000, size=periods)

    # Convert to Unix epoch seconds in a way that is independent of the
    # pandas internal datetime resolution. In pandas <=2.x DatetimeIndex
    # stored ns; in pandas 3.x the default is us — a raw
    # `index.astype('int64') // 10**9` silently scales the result by 1e3
    # and produced bogus 1970-01-20 timestamps in the agent loader tests.
    epoch_seconds = (
        (index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)
    ).to_numpy()
    frame = pd.DataFrame(
        {
            "ts": epoch_seconds,
            "open": open_prices,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
    frame.to_csv(path, index=False)


def build_system(tmp_path: Path) -> GeoSyncSystem:
    """Return a GeoSyncSystem wired with a simulated Binance connector."""

    venue = ExchangeAdapterConfig(name="binance", connector=BinanceConnector())
    settings = LiveLoopSettings(state_dir=tmp_path / "state")
    config = GeoSyncSystemConfig(venues=[venue], live_settings=settings)
    return GeoSyncSystem(config)
