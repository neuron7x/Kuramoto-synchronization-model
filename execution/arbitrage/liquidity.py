"""Liquidity management utilities for cross-venue arbitrage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock
from typing import Dict, Mapping

from .models import LiquiditySnapshot


@dataclass(slots=True)
class _LiquidityState:
    base_available: Decimal
    quote_available: Decimal
    base_reserved: Decimal = Decimal("0")
    quote_reserved: Decimal = Decimal("0")

    def clone(self) -> "_LiquidityState":
        return _LiquidityState(
            base_available=self.base_available,
            quote_available=self.quote_available,
            base_reserved=self.base_reserved,
            quote_reserved=self.quote_reserved,
        )


@dataclass(slots=True, frozen=True)
class LiquidityReservation:
    reservation_id: str
    exchange_id: str
    symbol: str
    base_amount: Decimal
    quote_amount: Decimal


class LiquidityError(RuntimeError):
    """Raised when liquidity operations cannot be satisfied."""


class LiquidityLedger:
    """Thread-safe ledger storing available liquidity per venue and symbol."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._balances: Dict[tuple[str, str], _LiquidityState] = {}
        self._reservations: Dict[str, LiquidityReservation] = {}

    def set_balance(
        self,
        exchange_id: str,
        symbol: str,
        *,
        base_available: Decimal,
        quote_available: Decimal,
    ) -> None:
        if base_available < Decimal("0") or quote_available < Decimal("0"):
            raise ValueError("balances cannot be negative")
        key = (exchange_id, symbol)
        with self._lock:
            state = self._balances.get(key)
            if state is None:
                state = _LiquidityState(base_available, quote_available)
                self._balances[key] = state
            else:
                if (
                    state.base_reserved > base_available
                    or state.quote_reserved > quote_available
                ):
                    raise LiquidityError(
                        "cannot set balances below outstanding reservations"
                    )
                state.base_available = base_available
                state.quote_available = quote_available

    def get_snapshot(self, exchange_id: str, symbol: str) -> LiquiditySnapshot | None:
        key = (exchange_id, symbol)
        with self._lock:
            state = self._balances.get(key)
            if state is None:
                return None
            return LiquiditySnapshot(
                exchange_id=exchange_id,
                symbol=symbol,
                base_available=state.base_available - state.base_reserved,
                quote_available=state.quote_available - state.quote_reserved,
                bid_liquidity=state.base_available,
                ask_liquidity=state.quote_available,
                timestamp=datetime.now(timezone.utc),
            )

    def reserve(
        self,
        reservation_id: str,
        exchange_id: str,
        symbol: str,
        *,
        base_amount: Decimal = Decimal("0"),
        quote_amount: Decimal = Decimal("0"),
    ) -> LiquidityReservation:
        if base_amount < Decimal("0") or quote_amount < Decimal("0"):
            raise ValueError("reservation amounts cannot be negative")
        key = (exchange_id, symbol)
        with self._lock:
            if reservation_id in self._reservations:
                raise LiquidityError(f"reservation_id {reservation_id} already exists")
            state = self._balances.get(key)
            if state is None:
                raise LiquidityError(
                    f"No balance configured for {exchange_id}:{symbol}"
                )
            available_base = state.base_available - state.base_reserved
            available_quote = state.quote_available - state.quote_reserved
            if base_amount > available_base or quote_amount > available_quote:
                raise LiquidityError("insufficient available liquidity to reserve")
            state.base_reserved += base_amount
            state.quote_reserved += quote_amount
            reservation = LiquidityReservation(
                reservation_id=reservation_id,
                exchange_id=exchange_id,
                symbol=symbol,
                base_amount=base_amount,
                quote_amount=quote_amount,
            )
            self._reservations[reservation_id] = reservation
            return reservation

    def release(self, reservation_id: str) -> None:
        with self._lock:
            reservation = self._reservations.pop(reservation_id, None)
            if reservation is None:
                return
            key = (reservation.exchange_id, reservation.symbol)
            state = self._balances.get(key)
            if state is None:
                return
            state.base_reserved -= reservation.base_amount
            state.quote_reserved -= reservation.quote_amount

    def commit(self, reservation_id: str) -> None:
        with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None:
                raise LiquidityError(f"Unknown reservation_id {reservation_id}")
            key = (reservation.exchange_id, reservation.symbol)
            state = self._balances.get(key)
            if state is None:
                raise LiquidityError(
                    f"Balance missing for reservation {reservation_id}"
                )
            if reservation.base_amount > state.base_reserved:
                raise LiquidityError("reserved base less than reservation")
            if reservation.quote_amount > state.quote_reserved:
                raise LiquidityError("reserved quote less than reservation")
            new_base_available = state.base_available - reservation.base_amount
            new_quote_available = state.quote_available - reservation.quote_amount
            if new_base_available < Decimal("0") or new_quote_available < Decimal("0"):
                raise LiquidityError("negative balance after commit")
            state.base_reserved -= reservation.base_amount
            state.quote_reserved -= reservation.quote_amount
            state.base_available = new_base_available
            state.quote_available = new_quote_available
            self._reservations.pop(reservation_id, None)

    def apply_fill(
        self,
        exchange_id: str,
        symbol: str,
        *,
        base_delta: Decimal = Decimal("0"),
        quote_delta: Decimal = Decimal("0"),
    ) -> None:
        key = (exchange_id, symbol)
        with self._lock:
            state = self._balances.get(key)
            if state is None:
                raise LiquidityError(
                    f"No balance configured for {exchange_id}:{symbol}"
                )
            state.base_available += base_delta
            state.quote_available += quote_delta
            if state.base_available < Decimal("0") or state.quote_available < Decimal(
                "0"
            ):
                raise LiquidityError("negative balance after fill application")

    def available_balances(self) -> Mapping[tuple[str, str], tuple[Decimal, Decimal]]:
        with self._lock:
            return {
                key: (
                    state.base_available - state.base_reserved,
                    state.quote_available - state.quote_reserved,
                )
                for key, state in self._balances.items()
            }
