# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Paper execution engine for the sandbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..models import (
    AuditEvent,
    ExecutionFill,
    ExecutionReport,
    OrderSide,
    OrderTicket,
    RiskDecision,
    TradingSignal,
)
from ..risk.engine import AuditLoggerProtocol


class SignalGatewayProtocol:
    async def generate(
        self, symbol: str
    ) -> TradingSignal:  # pragma: no cover - protocol definition
        raise NotImplementedError


class RiskGatewayProtocol:
    async def evaluate(
        self, order: OrderTicket, signal: TradingSignal
    ) -> RiskDecision:  # pragma: no cover
        raise NotImplementedError


@dataclass
class ExecutionParameters:
    slippage_bps: float


class ExecutionEngine:
    def __init__(
        self,
        *,
        signals: SignalGatewayProtocol,
        risk: RiskGatewayProtocol,
        audit: AuditLoggerProtocol,
        params: ExecutionParameters,
    ) -> None:
        self._signals = signals
        self._risk = risk
        self._audit = audit
        self._params = params

    async def execute(self, order: OrderTicket) -> ExecutionReport:
        signal = await self._signals.generate(order.symbol)
        decision = await self._risk.evaluate(order, signal)
        if not decision.approved:
            report = ExecutionReport(
                accepted=False,
                message=f"order_rejected::{decision.reason}",
                signal=signal,
                risk=decision,
                fills=[],
            )
            await self._audit.emit(
                AuditEvent(
                    source="execution-paper",
                    category="execution",
                    message="order_rejected",
                    created_at=datetime.now(timezone.utc),
                    payload={"symbol": order.symbol, "reason": decision.reason},
                )
            )
            return report

        fill_price = self._apply_slippage(signal.reference_price, order.side)
        fill = ExecutionFill(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            executed_at=datetime.now(timezone.utc),
        )
        report = ExecutionReport(
            accepted=True,
            message="order_filled",
            signal=signal,
            risk=decision,
            fills=[fill],
        )
        await self._audit.emit(
            AuditEvent(
                source="execution-paper",
                category="execution",
                message="order_filled",
                created_at=fill.executed_at,
                payload={
                    "symbol": order.symbol,
                    "price": fill.price,
                    "quantity": order.quantity,
                },
            )
        )
        return report

    def _apply_slippage(self, price: float, side: OrderSide) -> float:
        adjustment = price * (self._params.slippage_bps / 10_000)
        if side is OrderSide.BUY:
            return round(price + adjustment, 2)
        return round(price - adjustment, 2)
