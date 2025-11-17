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
