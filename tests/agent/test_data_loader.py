# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import pytest

from core.data.models import InstrumentType
from geosync_agent import AgentDataFeedConfig, AgentDataLoader

from .utils import build_system, write_sample_ohlc


@pytest.fixture()
def sample_feed(tmp_path: Path) -> Path:
    path = tmp_path / "sample.csv"
    write_sample_ohlc(path, periods=256)
    return path


def test_agent_data_loader_produces_feature_frame(tmp_path: Path, sample_feed: Path) -> None:
    system = build_system(tmp_path)
    loader = AgentDataLoader(system)
    config = AgentDataFeedConfig(
        path=sample_feed,
        symbol="BTCUSDT",
        venue="BINANCE",
        instrument_type=InstrumentType.SPOT,
    )

    market = loader.load_market_data(config)
    assert not market.empty
    assert market.index.tz is not None
    assert market.index.is_monotonic_increasing
    assert {"open", "high", "low", "close", "volume"}.issubset(market.columns)

    features = loader.build_feature_frame(market)
    assert "rsi" in features.columns
    assert features.index.equals(market.index[-len(features) :])
    assert features.isna().sum().sum() == 0

    loaded = loader.load(config)
    assert loaded.market_frame.shape[0] == loaded.feature_frame.shape[0]
    assert loaded.feature_frame.index.equals(loaded.market_frame.index)
    assert loaded.feature_frame.columns.difference(loaded.market_frame.columns).tolist()


def test_agent_data_loader_rejects_insufficient_rows(tmp_path: Path) -> None:
    system = build_system(tmp_path)
    loader = AgentDataLoader(system)
    path = tmp_path / "tiny.csv"
    write_sample_ohlc(path, periods=4)
    config = AgentDataFeedConfig(path=path, symbol="ETHUSDT", venue="BINANCE")

    market = loader.load_market_data(config)
    assert market.shape[0] == 4
    with pytest.raises(ValueError):
        loader.load(config)
