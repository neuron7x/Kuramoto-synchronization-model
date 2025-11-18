"""Test helpers for TradePulse agent integration tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from application.system import (
    ExchangeAdapterConfig,
    LiveLoopSettings,
    TradePulseSystem,
    TradePulseSystemConfig,
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

    frame = pd.DataFrame(
        {
            "ts": index.astype("int64") // 10**9,
            "open": open_prices,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
    frame.to_csv(path, index=False)


def build_system(tmp_path: Path) -> TradePulseSystem:
    """Return a TradePulseSystem wired with a simulated Binance connector."""

    venue = ExchangeAdapterConfig(name="binance", connector=BinanceConnector())
    settings = LiveLoopSettings(state_dir=tmp_path / "state")
    config = TradePulseSystemConfig(venues=[venue], live_settings=settings)
    return TradePulseSystem(config)
