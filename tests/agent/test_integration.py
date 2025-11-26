from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np

from domain import Signal
from tradepulse.sdk import SDKConfig, TradePulseSDK
from tradepulse_agent import (
    AgentAction,
    AgentDataFeedConfig,
    AgentDataLoader,
    AgentEnvironmentConfig,
    AgentExecutionConfig,
    AgentTradeOrchestrator,
    TradingAgentEnvironment,
)

from .utils import build_system, write_sample_ohlc


def _position_sizer(signal: Signal) -> float:
    metadata = signal.metadata or {}
    quantity = metadata.get("quantity")
    return float(quantity) if quantity is not None else 0.1


def _factory(prefix: str) -> callable:
    counter = deque(range(1, 1_000))

    def _next() -> str:
        return f"{prefix}-{counter.popleft()}"

    return _next


def test_agent_trade_orchestrator_executes_order(tmp_path: Path) -> None:
    system = build_system(tmp_path)
    path = tmp_path / "market.csv"
    write_sample_ohlc(path, periods=256)

    loader = AgentDataLoader(system)
    env_config = AgentEnvironmentConfig(
        lookback_window=32,
        initial_cash=5_000.0,
        max_position=0.5,
        position_increment=0.25,
        trading_fee_bps=2.0,
    )
    feed_config = AgentDataFeedConfig(path=path, symbol="BTCUSDT", venue="BINANCE")
    environment = TradingAgentEnvironment(system, loader, feed_config, env_config)
    observation = environment.reset()

    sdk_config = SDKConfig(
        default_venue="binance",
        signal_strategy=lambda prices: np.zeros_like(prices),
        position_sizer=_position_sizer,
        correlation_id_factory=_factory("corr"),
        session_id_factory=_factory("session"),
    )
    sdk = TradePulseSDK(system, sdk_config)

    execution_config = AgentExecutionConfig(
        position_increment=env_config.position_increment,
        max_position=env_config.max_position,
        min_confidence=0.6,
        confidence_scale=0.5,
    )
    orchestrator = AgentTradeOrchestrator(
        sdk,
        symbol="BTCUSDT",
        venue="BINANCE",
        execution_config=execution_config,
        price_column=system.feature_pipeline.config.price_col,
    )

    result = orchestrator.execute_action(AgentAction.BUY, observation)

    assert result.signal is not None
    assert result.suggested_order is not None
    assert result.risk_result is not None
    assert getattr(result.risk_result, "approved", False)
    assert result.execution is not None

    audit_log = sdk.get_audit_log(result.execution.session_id)
    events = {event.event for event in audit_log}
    assert {"trade_proposed", "risk_check_passed", "order_submitted"}.issubset(events)

    # Execute a sell to flatten the position
    next_observation = environment.step(AgentAction.BUY).observation
    sell_result = orchestrator.execute_action(AgentAction.SELL, next_observation)
    assert sell_result.signal is not None
