# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Implementation of the GeoSync public SDK contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isclose, isnan
from typing import Mapping, MutableMapping, TypeVar

from application.system import GeoSyncSystem
from domain import Order, OrderSide, OrderType, Signal, SignalAction

from .contracts import (
    AuditEvent,
    ExecutionResult,
    MarketState,
    RiskCheckResult,
    SDKConfig,
    SuggestedOrder,
    utc_now,
)

__all__ = ["GeoSyncSDK"]

_E = TypeVar("_E", bound=Enum)


def _enum_value(val: _E | str) -> str:
    """Extract the string value from an enum or passthrough string."""
    return val.value if isinstance(val, Enum) else val


@dataclass(slots=True)
class _SymbolContext:
    venue: str
    last_price: float | None


@dataclass(slots=True)
class _SessionState:
    order: Order
    venue: str
    events: list[AuditEvent] = field(default_factory=list)
    approved: bool | None = None


class GeoSyncSDK:
    """Orchestrate trading operations via the public SDK contract."""

    def __init__(self, system: GeoSyncSystem, config: SDKConfig) -> None:
        self._system = system
        self._config = config
        self._price_column = system.feature_pipeline.config.price_col
        self._contexts: MutableMapping[str, _SymbolContext] = {}
        self._sessions: MutableMapping[str, _SessionState] = {}
        self._order_session: MutableMapping[int, str] = {}

    # ------------------------------------------------------------------
    # Contract methods
    def get_signal(self, market_state: MarketState) -> Signal:
        """Derive a trading signal for the supplied *market_state*."""

        strategy = market_state.strategy or self._config.signal_strategy
        feature_frame = self._system.build_feature_frame(market_state.market_frame)
        signals = self._system.generate_signals(
            feature_frame, strategy=strategy, symbol=market_state.symbol
        )
        if not signals:
            raise ValueError("No signals generated for the provided market state")

        signal = signals[-1]
        last_price = None
        if self._price_column in feature_frame.columns:
            last_price = float(feature_frame[self._price_column].iloc[-1])

        venue_key = self._resolve_venue(market_state.symbol, market_state.venue)
        self._contexts[market_state.symbol] = _SymbolContext(venue=venue_key, last_price=last_price)
        return signal

    def propose_trade(self, signal: Signal) -> SuggestedOrder:
        """Produce an order proposal for *signal*."""

        context = self._contexts.get(signal.symbol)
        if context is None:
            raise LookupError(
                f"No market context available for symbol {signal.symbol!r}; call get_signal first"
            )
        if signal.action in {SignalAction.HOLD}:
            raise ValueError("Cannot propose trade for HOLD signals")

        try:
            current_position = float(self._system.risk_manager.current_position(signal.symbol))
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"Risk manager returned invalid position for symbol {signal.symbol!r}"
            ) from exc

        if signal.action is SignalAction.EXIT:
            if isnan(current_position) or isclose(current_position, 0.0, abs_tol=1e-9):
                raise ValueError(f"Cannot exit flat position for symbol {signal.symbol!r}")
            quantity = abs(current_position)
            side = OrderSide.SELL if current_position > 0 else OrderSide.BUY
        elif signal.action is SignalAction.SELL:
            raw_quantity = float(self._config.position_sizer(signal))
            quantity = abs(raw_quantity)
            if quantity == 0:
                raise ValueError("Position sizer must return a non-zero quantity")
            side = OrderSide.SELL
        else:
            raw_quantity = float(self._config.position_sizer(signal))
            quantity = abs(raw_quantity)
            if quantity == 0:
                raise ValueError("Position sizer must return a non-zero quantity")
            side = OrderSide.BUY

        price = context.last_price
        order_type = OrderType.MARKET if price is None else OrderType.LIMIT
        order = Order(
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
        )

        session_id = self._config.session_id_factory()
        state = _SessionState(order=order, venue=context.venue)
        self._sessions[session_id] = state
        self._order_session[id(order)] = session_id
        self._record_event(
            session_id,
            "trade_proposed",
            {
                "symbol": signal.symbol,
                "side": _enum_value(order.side),
                "quantity": order.quantity,
                "price": order.price,
                "action": _enum_value(signal.action),
                "confidence": signal.confidence,
            },
        )
        rationale = (
            "Exit position requested by signal"
            if signal.action is SignalAction.EXIT
            else "Derived from signal action"
        )
        return SuggestedOrder(
            order=order,
            session_id=session_id,
            venue=context.venue,
            rationale=rationale,
        )

    def risk_check(self, order: Order) -> RiskCheckResult:
        """Run the core risk controls against *order*."""

        session_id = self._resolve_session(order)
        state = self._sessions[session_id]

        price = order.price
        if price is None:
            context = self._contexts.get(order.symbol)
            if context is None or context.last_price is None:
                raise ValueError("No reference price available for risk assessment")
            price = context.last_price
            order.price = price

        try:
            self._system.risk_manager.validate_order(
                order.symbol, _enum_value(order.side), order.quantity, float(price)
            )
        except Exception as exc:
            state.approved = False
            reason = str(exc)
            self._record_event(
                session_id,
                "risk_check_failed",
                {
                    "symbol": order.symbol,
                    "side": _enum_value(order.side),
                    "quantity": order.quantity,
                    "price": price,
                    "error": reason,
                    "exception": exc.__class__.__name__,
                },
            )
            return RiskCheckResult(False, reason, session_id)

        state.approved = True
        self._record_event(
            session_id,
            "risk_check_passed",
            {
                "symbol": order.symbol,
                "side": _enum_value(order.side),
                "quantity": order.quantity,
                "price": price,
            },
        )
        return RiskCheckResult(True, None, session_id)

    def execute(self, order: Order) -> ExecutionResult:
        """Submit *order* to the execution loop."""

        session_id = self._resolve_session(order)
        state = self._sessions[session_id]
        if state.approved is None:
            result = self.risk_check(order)
            if not result.approved:
                raise RuntimeError("Order failed risk validation and cannot be executed")
            state = self._sessions[session_id]

        if state.approved is False:
            raise RuntimeError("Order was rejected by risk checks and cannot be executed")

        venue = state.venue or self._config.default_venue
        correlation_id = self._config.correlation_id_factory()
        loop = self._system.ensure_live_loop()
        submitted = loop.submit_order(venue, order, correlation_id=correlation_id)
        state.order = submitted
        self._order_session[id(submitted)] = session_id
        self._record_event(
            session_id,
            "order_submitted",
            {
                "symbol": submitted.symbol,
                "side": _enum_value(submitted.side),
                "quantity": submitted.quantity,
                "price": submitted.price,
                "venue": venue,
                "correlation_id": correlation_id,
            },
        )
        return ExecutionResult(
            session_id=session_id,
            order=submitted,
            correlation_id=correlation_id,
            venue=venue,
        )

    def get_audit_log(self, session_id: str) -> tuple[AuditEvent, ...]:
        """Return the immutable audit trail for *session_id*."""

        state = self._sessions.get(session_id)
        if state is None:
            return tuple()
        return tuple(state.events)

    # ------------------------------------------------------------------
    # Internal helpers
    def _resolve_session(self, order: Order) -> str:
        session_id = self._order_session.get(id(order))
        if session_id is not None:
            return session_id
        for key, state in self._sessions.items():
            if state.order is order:
                self._order_session[id(order)] = key
                return key
        raise LookupError("Order is not managed by the GeoSync SDK")

    def _record_event(self, session_id: str, event: str, payload: Mapping[str, object]) -> None:
        timestamp = utc_now()
        entry = AuditEvent(
            session_id=session_id,
            event=event,
            timestamp=timestamp,
            payload=dict(payload),
        )
        state = self._sessions.get(session_id)
        if state is None:
            return
        state.events.append(entry)

    def _resolve_venue(self, symbol: str, declared: str) -> str:
        key = symbol.lower()
        overrides = self._config.venue_overrides
        if overrides:
            override = overrides.get(key) or overrides.get(symbol)
            if override:
                return override.lower()
        return declared.lower()
