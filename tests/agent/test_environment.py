# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from geosync_agent import (
    AgentAction,
    AgentDataFeedConfig,
    AgentDataLoader,
    AgentEnvironmentConfig,
    TradingAgentEnvironment,
)

from .utils import build_system, write_sample_ohlc


def test_environment_reset_and_step(tmp_path: Path) -> None:
    system = build_system(tmp_path)
    path = tmp_path / "market.csv"
    write_sample_ohlc(path, periods=256)
    loader = AgentDataLoader(system)
    env_config = AgentEnvironmentConfig(
        lookback_window=32,
        initial_cash=10_000.0,
        max_position=0.5,
        position_increment=0.25,
        trading_fee_bps=5.0,
    )
    feed_config = AgentDataFeedConfig(path=path, symbol="BTCUSDT", venue="BINANCE")
    env = TradingAgentEnvironment(system, loader, feed_config, env_config)

    observation = env.reset()
    assert observation.feature_matrix.shape == (
        env_config.lookback_window,
        observation.feature_window.shape[1],
    )
    assert observation.position == pytest.approx(0.0)
    assert observation.cash == pytest.approx(env_config.initial_cash)

    result = env.step(AgentAction.BUY)
    assert not result.done
    assert result.info["position"] == pytest.approx(env_config.position_increment)
    assert np.isfinite(result.reward)

    result = env.step(AgentAction.SELL)
    assert np.isfinite(result.reward)
    assert result.info["position"] == pytest.approx(0.0)


def test_environment_requires_reset(tmp_path: Path) -> None:
    system = build_system(tmp_path)
    path = tmp_path / "market.csv"
    write_sample_ohlc(path, periods=128)
    loader = AgentDataLoader(system)
    env_config = AgentEnvironmentConfig(lookback_window=16)
    feed_config = AgentDataFeedConfig(path=path, symbol="ETHUSDT", venue="BINANCE")
    env = TradingAgentEnvironment(system, loader, feed_config, env_config)

    with pytest.raises(RuntimeError):
        env.step(AgentAction.BUY)

    env.reset()
    for _ in range(4):
        env.step(AgentAction.HOLD)
