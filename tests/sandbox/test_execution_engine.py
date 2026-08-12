# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from datetime import datetime, timezone

import pytest

from sandbox.execution.engine import ExecutionEngine, ExecutionParameters
from sandbox.models import (
    AuditEvent,
    ExecutionReport,
    OrderSide,
    OrderTicket,
    RiskDecision,
    SignalDirection,
    TradingSignal,
)
from sandbox.risk.engine import AuditLoggerProtocol


class StubSignalGateway:
    def __init__(self, signal: TradingSignal) -> None:
        self._signal = signal

    async def generate(self, symbol: str) -> TradingSignal:
        return self._signal


class StubRiskGateway:
    def __init__(self, decisions: list[RiskDecision]) -> None:
        self._decisions = decisions
        self._index = 0

    async def evaluate(self, order: OrderTicket, signal: TradingSignal) -> RiskDecision:
        decision = self._decisions[min(self._index, len(self._decisions) - 1)]
        self._index += 1
        return decision


class StubAudit(AuditLoggerProtocol):
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_execution_engine_respects_risk_rejection() -> None:
    signal = TradingSignal(
        symbol="btcusd",
        generated_at=datetime.now(timezone.utc),
        direction=SignalDirection.BUY,
        strength=0.01,
        reference_price=100.0,
        rationale="test",
    )
    risk_decision = RiskDecision(approved=False, reason="limits_exceeded", limit_consumption=1.0)
    audit = StubAudit()
    engine = ExecutionEngine(
        signals=StubSignalGateway(signal),
        risk=StubRiskGateway([risk_decision]),
        audit=audit,
        params=ExecutionParameters(slippage_bps=5.0),
    )
    order = OrderTicket(symbol="btcusd", side=OrderSide.BUY, quantity=1)
    report = await engine.execute(order)
    assert not report.accepted
    assert report.message.startswith("order_rejected")
    assert audit.events


@pytest.mark.asyncio
async def test_execution_engine_creates_fill_when_risk_approves() -> None:
    signal = TradingSignal(
        symbol="btcusd",
        generated_at=datetime.now(timezone.utc),
        direction=SignalDirection.BUY,
        strength=0.02,
        reference_price=100.0,
        rationale="test",
    )
    risk_decision = RiskDecision(approved=True, reason="approved", limit_consumption=0.5)
    audit = StubAudit()
    engine = ExecutionEngine(
        signals=StubSignalGateway(signal),
        risk=StubRiskGateway([risk_decision]),
        audit=audit,
        params=ExecutionParameters(slippage_bps=10.0),
    )
    order = OrderTicket(symbol="btcusd", side=OrderSide.SELL, quantity=1.5)
    report: ExecutionReport = await engine.execute(order)
    assert report.accepted
    assert report.fills[0].price == 99.9
    assert len(audit.events) == 1
