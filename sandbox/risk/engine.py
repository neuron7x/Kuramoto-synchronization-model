"""Risk evaluation logic for the sandbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock

from ..models import (
    AuditEvent,
    KillSwitchState,
    OrderSide,
    OrderTicket,
    RiskDecision,
    SignalDirection,
    TradingSignal,
)


class KillSwitchProviderProtocol:
    async def state(self) -> KillSwitchState:  # pragma: no cover - protocol definition
        raise NotImplementedError


class AuditLoggerProtocol:
    async def emit(
        self, event: AuditEvent
    ) -> None:  # pragma: no cover - protocol definition
        raise NotImplementedError


@dataclass
class RiskLimits:
    max_position: float
    max_notional: float


class RiskEngine:
    """Deterministic risk checks suitable for demonstrations."""

    def __init__(
        self,
        *,
        limits: RiskLimits,
        kill_switch: KillSwitchProviderProtocol,
        audit_logger: AuditLoggerProtocol,
    ) -> None:
        self._limits = limits
        self._kill_switch = kill_switch
        self._audit = audit_logger
        self._positions: dict[str, float] = {}
        self._lock = Lock()

    async def evaluate(self, order: OrderTicket, signal: TradingSignal) -> RiskDecision:
        state = await self._kill_switch.state()
        now = datetime.now(timezone.utc)
        if state.engaged:
            decision = RiskDecision(
                approved=False,
                reason=state.reason or "kill_switch_engaged",
                limit_consumption=1.0,
            )
            await self._audit.emit(
                AuditEvent(
                    source="risk-engine",
                    category="risk",
                    message="order_rejected_kill_switch",
                    created_at=now,
                    payload={"symbol": order.symbol, "reason": decision.reason},
                )
            )
            return decision

        if signal.direction is SignalDirection.HOLD:
            decision = RiskDecision(
                approved=False, reason="neutral_signal", limit_consumption=0.0
            )
            await self._audit.emit(
                AuditEvent(
                    source="risk-engine",
                    category="risk",
                    message="order_rejected_signal_hold",
                    created_at=now,
                    payload={"symbol": order.symbol},
                )
            )
            return decision

        if (
            signal.direction is SignalDirection.BUY and order.side is not OrderSide.BUY
        ) or (
            signal.direction is SignalDirection.SELL
            and order.side is not OrderSide.SELL
        ):
            decision = RiskDecision(
                approved=False,
                reason="signal_direction_mismatch",
                limit_consumption=0.0,
            )
            await self._audit.emit(
                AuditEvent(
                    source="risk-engine",
                    category="risk",
                    message="order_rejected_signal_mismatch",
                    created_at=now,
                    payload={"symbol": order.symbol},
                )
            )
            return decision

        signed_quantity = (
            order.quantity if order.side is OrderSide.BUY else -order.quantity
        )
        notional = order.quantity * signal.reference_price

        with self._lock:
            current_position = self._positions.get(order.symbol, 0.0)
            proposed = current_position + signed_quantity
            position_consumption = min(abs(proposed) / self._limits.max_position, 1.0)
            notional_consumption = min(notional / self._limits.max_notional, 1.0)
            limit_consumption = max(position_consumption, notional_consumption)
            if (
                abs(proposed) > self._limits.max_position
                or notional > self._limits.max_notional
            ):
                decision = RiskDecision(
                    approved=False,
                    reason="limits_exceeded",
                    limit_consumption=limit_consumption,
                )
            else:
                self._positions[order.symbol] = proposed
                decision = RiskDecision(
                    approved=True,
                    reason="approved",
                    limit_consumption=limit_consumption,
                )

        await self._audit.emit(
            AuditEvent(
                source="risk-engine",
                category="risk",
                message="order_evaluated",
                created_at=now,
                payload={
                    "symbol": order.symbol,
                    "approved": decision.approved,
                    "limit_consumption": decision.limit_consumption,
                },
            )
        )
        return decision
