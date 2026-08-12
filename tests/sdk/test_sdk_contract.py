# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from application.system import (
    ExchangeAdapterConfig,
    GeoSyncSystem,
    GeoSyncSystemConfig,
    LiveLoopSettings,
)
from domain import Order, OrderSide, Signal, SignalAction
from execution.connectors import BinanceConnector
from execution.risk import RiskLimits
from geosync.sdk import (
    GeoSyncSDK,
    MarketState,
    SDKConfig,
    SuggestedOrder,
)


class _FakeLiveLoop:
    """Test double capturing submitted orders without network IO."""

    def __init__(self) -> None:
        self.submitted: list[tuple[str, Order, str]] = []

    def submit_order(self, venue: str, order: Order, *, correlation_id: str) -> Order:
        cloned = Order(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.price,
            order_type=order.order_type,
        )
        self.submitted.append((venue, cloned, correlation_id))
        return cloned


def _strategy(prices: np.ndarray) -> np.ndarray:
    """Simple directional strategy used in contract tests."""

    gradients = np.gradient(prices)
    signals = np.where(gradients >= 0.0, 1.0, -1.0)
    if signals[-1] == 0.0:
        signals[-1] = 1.0
    return signals


def _position_sizer(signal) -> float:
    return max(signal.confidence, 0.25)


def _build_system(tmp_path: Path, *, risk_limits: RiskLimits | None = None) -> GeoSyncSystem:
    venue = ExchangeAdapterConfig(name="BINANCE", connector=BinanceConnector())
    settings = LiveLoopSettings(state_dir=tmp_path / "state")
    config = GeoSyncSystemConfig(
        venues=[venue],
        live_settings=settings,
        risk_limits=risk_limits or RiskLimits(max_notional=1_000_000.0, max_position=1_000.0),
    )
    return GeoSyncSystem(config)


def _load_market_frame(system: GeoSyncSystem) -> pd.DataFrame:
    data_path = Path(__file__).resolve().parents[2] / "data" / "sample.csv"
    frame = system.ingest_csv(data_path, symbol="BTCUSDT", venue="BINANCE")
    return frame


def test_sdk_happy_path(tmp_path: Path) -> None:
    system = _build_system(tmp_path)
    market = _load_market_frame(system)
    config = SDKConfig(
        default_venue="binance",
        signal_strategy=_strategy,
        position_sizer=_position_sizer,
    )
    sdk = GeoSyncSDK(system, config)

    state = MarketState(symbol="BTCUSDT", venue="BINANCE", market_frame=market)
    signal = sdk.get_signal(state)
    assert signal.symbol == "BTCUSDT"
    assert signal.action in {SignalAction.BUY, SignalAction.SELL}

    proposal = sdk.propose_trade(signal)
    assert isinstance(proposal, SuggestedOrder)
    assert proposal.order.quantity > 0
    assert proposal.venue == "binance"

    risk_result = sdk.risk_check(proposal.order)
    assert risk_result.approved is True
    assert risk_result.reason is None

    fake_loop = _FakeLiveLoop()
    system.ensure_live_loop = lambda: fake_loop  # type: ignore[assignment]

    execution = sdk.execute(proposal.order)
    assert execution.session_id == proposal.session_id
    assert fake_loop.submitted
    venue, submitted_order, correlation = fake_loop.submitted[-1]
    assert venue == "binance"
    assert submitted_order.symbol == "BTCUSDT"
    assert submitted_order.side in {OrderSide.BUY, OrderSide.SELL}
    assert correlation == execution.correlation_id

    events = sdk.get_audit_log(execution.session_id)
    assert [event.event for event in events] == [
        "trade_proposed",
        "risk_check_passed",
        "order_submitted",
    ]


def test_risk_check_rejection(tmp_path: Path) -> None:
    limits = RiskLimits(max_notional=10.0, max_position=0.5)
    system = _build_system(tmp_path, risk_limits=limits)
    market = _load_market_frame(system)
    config = SDKConfig(
        default_venue="binance",
        signal_strategy=_strategy,
        position_sizer=lambda signal: 1.0,
    )
    sdk = GeoSyncSDK(system, config)

    signal = sdk.get_signal(MarketState(symbol="BTCUSDT", venue="BINANCE", market_frame=market))
    proposal = sdk.propose_trade(signal)

    result = sdk.risk_check(proposal.order)
    assert result.approved is False
    assert "exceeded" in (result.reason or "")

    events = sdk.get_audit_log(result.session_id)
    assert events[-1].event == "risk_check_failed"


def test_propose_trade_requires_context(tmp_path: Path) -> None:
    system = _build_system(tmp_path)
    config = SDKConfig(
        default_venue="binance",
        signal_strategy=_strategy,
        position_sizer=_position_sizer,
    )
    sdk = GeoSyncSDK(system, config)

    with pytest.raises(LookupError):
        signal = type(
            "_S",
            (),
            {"symbol": "BTCUSDT", "action": SignalAction.BUY, "confidence": 0.5},
        )()
        sdk.propose_trade(signal)  # type: ignore[arg-type]


def test_exit_short_position_requests_buy_order(tmp_path: Path, monkeypatch) -> None:
    system = _build_system(tmp_path)
    market = _load_market_frame(system)
    config = SDKConfig(
        default_venue="binance",
        signal_strategy=_strategy,
        position_sizer=_position_sizer,
    )
    sdk = GeoSyncSDK(system, config)

    state = MarketState(symbol="BTCUSDT", venue="BINANCE", market_frame=market)
    sdk.get_signal(state)

    monkeypatch.setattr(system.risk_manager, "current_position", lambda symbol: -0.75)

    exit_signal = Signal(symbol="BTCUSDT", action=SignalAction.EXIT, confidence=1.0)
    proposal = sdk.propose_trade(exit_signal)

    assert proposal.order.side is OrderSide.BUY
    assert proposal.order.quantity > 0


def test_exit_order_uses_position_size(tmp_path: Path, monkeypatch) -> None:
    system = _build_system(tmp_path)
    market = _load_market_frame(system)
    config = SDKConfig(
        default_venue="binance",
        signal_strategy=_strategy,
        position_sizer=_position_sizer,
    )
    sdk = GeoSyncSDK(system, config)

    state = MarketState(symbol="BTCUSDT", venue="BINANCE", market_frame=market)
    sdk.get_signal(state)

    monkeypatch.setattr(system.risk_manager, "current_position", lambda symbol: 2.5)

    exit_signal = Signal(symbol="BTCUSDT", action=SignalAction.EXIT, confidence=1.0)
    proposal = sdk.propose_trade(exit_signal)

    assert proposal.order.quantity == pytest.approx(2.5)
    assert proposal.order.side is OrderSide.SELL


def test_exit_flat_position_raises(tmp_path: Path, monkeypatch) -> None:
    system = _build_system(tmp_path)
    market = _load_market_frame(system)
    config = SDKConfig(
        default_venue="binance",
        signal_strategy=_strategy,
        position_sizer=_position_sizer,
    )
    sdk = GeoSyncSDK(system, config)

    state = MarketState(symbol="BTCUSDT", venue="BINANCE", market_frame=market)
    sdk.get_signal(state)

    monkeypatch.setattr(system.risk_manager, "current_position", lambda symbol: 0.0)

    exit_signal = Signal(symbol="BTCUSDT", action=SignalAction.EXIT, confidence=1.0)

    with pytest.raises(ValueError):
        sdk.propose_trade(exit_signal)
