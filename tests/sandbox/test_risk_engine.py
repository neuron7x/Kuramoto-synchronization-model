# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from datetime import datetime, timezone

import pytest

from sandbox.models import (
    AuditEvent,
    KillSwitchState,
    OrderSide,
    OrderTicket,
    SignalDirection,
    TradingSignal,
)
from sandbox.risk.engine import (
    AuditLoggerProtocol,
    KillSwitchProviderProtocol,
    RiskEngine,
    RiskLimits,
)


class StubKillSwitch(KillSwitchProviderProtocol):
    def __init__(self, engaged: bool = False) -> None:
        self._state = KillSwitchState(engaged=engaged, reason="maintenance" if engaged else None)

    async def state(self) -> KillSwitchState:
        return self._state


class StubAuditLogger(AuditLoggerProtocol):
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_risk_engine_rejects_when_kill_switch_engaged() -> None:
    engine = RiskEngine(
        limits=RiskLimits(max_position=10.0, max_notional=1000.0),
        kill_switch=StubKillSwitch(engaged=True),
        audit_logger=StubAuditLogger(),
    )
    order = OrderTicket(symbol="btcusd", side=OrderSide.BUY, quantity=1)
    signal = TradingSignal(
        symbol="btcusd",
        generated_at=datetime.now(timezone.utc),
        direction=SignalDirection.BUY,
        strength=0.01,
        reference_price=100.0,
        rationale="test",
    )

    decision = await engine.evaluate(order, signal)
    assert not decision.approved
    assert decision.reason == "maintenance"


@pytest.mark.asyncio
async def test_risk_engine_tracks_position_limits() -> None:
    logger = StubAuditLogger()
    engine = RiskEngine(
        limits=RiskLimits(max_position=5.0, max_notional=1000.0),
        kill_switch=StubKillSwitch(engaged=False),
        audit_logger=logger,
    )
    signal = TradingSignal(
        symbol="btcusd",
        generated_at=datetime.now(timezone.utc),
        direction=SignalDirection.BUY,
        strength=0.01,
        reference_price=50.0,
        rationale="test",
    )
    order = OrderTicket(symbol="btcusd", side=OrderSide.BUY, quantity=4.0)
    decision = await engine.evaluate(order, signal)
    assert decision.approved
    second_order = OrderTicket(symbol="btcusd", side=OrderSide.BUY, quantity=2.0)
    decision_second = await engine.evaluate(second_order, signal)
    assert not decision_second.approved
    assert decision_second.reason == "limits_exceeded"
    assert any(event.message == "order_evaluated" for event in logger.events)


@pytest.mark.asyncio
async def test_risk_engine_rejects_hold_signal() -> None:
    """Test that HOLD signals are rejected."""
    logger = StubAuditLogger()
    engine = RiskEngine(
        limits=RiskLimits(max_position=10.0, max_notional=1000.0),
        kill_switch=StubKillSwitch(engaged=False),
        audit_logger=logger,
    )
    signal = TradingSignal(
        symbol="btcusd",
        generated_at=datetime.now(timezone.utc),
        direction=SignalDirection.HOLD,
        strength=0.0,
        reference_price=100.0,
        rationale="neutral",
    )
    order = OrderTicket(symbol="btcusd", side=OrderSide.BUY, quantity=1.0)
    decision = await engine.evaluate(order, signal)
    assert not decision.approved
    assert decision.reason == "neutral_signal"


@pytest.mark.asyncio
async def test_risk_engine_rejects_signal_direction_mismatch() -> None:
    """Test that orders mismatching signal direction are rejected."""
    logger = StubAuditLogger()
    engine = RiskEngine(
        limits=RiskLimits(max_position=10.0, max_notional=1000.0),
        kill_switch=StubKillSwitch(engaged=False),
        audit_logger=logger,
    )
    signal = TradingSignal(
        symbol="btcusd",
        generated_at=datetime.now(timezone.utc),
        direction=SignalDirection.SELL,
        strength=0.05,
        reference_price=100.0,
        rationale="overbought",
    )
    order = OrderTicket(symbol="btcusd", side=OrderSide.BUY, quantity=1.0)
    decision = await engine.evaluate(order, signal)
    assert not decision.approved
    assert decision.reason == "signal_direction_mismatch"


@pytest.mark.asyncio
async def test_risk_engine_tracks_notional_limits() -> None:
    """Test that notional limits are enforced."""
    logger = StubAuditLogger()
    engine = RiskEngine(
        limits=RiskLimits(max_position=100.0, max_notional=500.0),
        kill_switch=StubKillSwitch(engaged=False),
        audit_logger=logger,
    )
    signal = TradingSignal(
        symbol="btcusd",
        generated_at=datetime.now(timezone.utc),
        direction=SignalDirection.BUY,
        strength=0.05,
        reference_price=100.0,
        rationale="test",
    )
    order = OrderTicket(symbol="btcusd", side=OrderSide.BUY, quantity=6.0)
    decision = await engine.evaluate(order, signal)
    assert not decision.approved
    assert decision.reason == "limits_exceeded"


@pytest.mark.asyncio
async def test_risk_engine_sell_reduces_position() -> None:
    """Test that sell orders reduce the position."""
    logger = StubAuditLogger()
    engine = RiskEngine(
        limits=RiskLimits(max_position=5.0, max_notional=1000.0),
        kill_switch=StubKillSwitch(engaged=False),
        audit_logger=logger,
    )
    buy_signal = TradingSignal(
        symbol="btcusd",
        generated_at=datetime.now(timezone.utc),
        direction=SignalDirection.BUY,
        strength=0.05,
        reference_price=100.0,
        rationale="buy",
    )
    sell_signal = TradingSignal(
        symbol="btcusd",
        generated_at=datetime.now(timezone.utc),
        direction=SignalDirection.SELL,
        strength=0.05,
        reference_price=100.0,
        rationale="sell",
    )
    buy_order = OrderTicket(symbol="btcusd", side=OrderSide.BUY, quantity=4.0)
    await engine.evaluate(buy_order, buy_signal)

    sell_order = OrderTicket(symbol="btcusd", side=OrderSide.SELL, quantity=2.0)
    decision = await engine.evaluate(sell_order, sell_signal)
    assert decision.approved

    another_buy = OrderTicket(symbol="btcusd", side=OrderSide.BUY, quantity=3.0)
    decision = await engine.evaluate(another_buy, buy_signal)
    assert decision.approved
