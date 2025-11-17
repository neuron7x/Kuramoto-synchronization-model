# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Sandbox-friendly broker connectors for major exchanges."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import replace
from typing import Deque, Dict, Iterable, List, Mapping
from uuid import uuid4

from domain import Order, OrderSide, OrderStatus

from .normalization import NormalizationError, SymbolNormalizer, SymbolSpecification

try:  # pragma: no cover - optional import for live connectors
    from execution.adapters import (
        BinanceRESTConnector,
        CoinbaseRESTConnector,
        KrakenRESTConnector,
    )
except (
    Exception
):  # pragma: no cover - adapters may not be available in minimal installs
    BinanceRESTConnector = None  # type: ignore[assignment]
    CoinbaseRESTConnector = None  # type: ignore[assignment]
    KrakenRESTConnector = None  # type: ignore[assignment]


class OrderError(RuntimeError):
    """Raised when a connector fails to process an order."""


class TransientOrderError(OrderError):
    """Recoverable connector failure that should be retried."""


class ExecutionConnector:
    """Minimal connector interface shared across exchanges."""

    def __init__(self, *, sandbox: bool = True) -> None:
        self.sandbox = sandbox
        self._orders: Dict[str, Order] = {}
        self._idempotency_cache: Dict[str, Order] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Helpers shared by default implementations
    def _generate_order_id(self) -> str:
        """Return a unique identifier suitable for offline connectors."""

        return uuid4().hex

    def _clone(self, order: Order) -> Order:
        """Create a shallow copy of ``order`` preserving dataclass invariants."""

        return replace(order)

    def connect(self, credentials: Mapping[str, str] | None = None) -> None:
        """Connect to the venue. Sandbox connectors are no-ops."""

    def disconnect(self) -> None:
        """Disconnect from the venue."""

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        with self._lock:
            if idempotency_key is not None:
                cached = self._idempotency_cache.get(idempotency_key)
                if cached is not None:
                    return cached

            submitted = self._clone(order)
            if not submitted.order_id:
                submitted.mark_submitted(self._generate_order_id())
            else:
                # If the caller provided an identifier we still ensure the order
                # transitions into an active state to mirror live venue behaviour.
                if submitted.status is OrderStatus.PENDING:
                    submitted.status = OrderStatus.OPEN

            if not submitted.order_id:
                # ``mark_submitted`` guarantees an identifier, but guard for
                # defensive programming should ``order_id`` be cleared
                # elsewhere.
                submitted.mark_submitted(self._generate_order_id())
            self._orders[submitted.order_id] = submitted
            if idempotency_key is not None:
                self._idempotency_cache[idempotency_key] = submitted
            return submitted

    def cancel_order(self, order_id: str) -> bool:
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                return False
            order.cancel()
        return True

    def fetch_order(self, order_id: str) -> Order:
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                raise OrderError(f"Unknown order_id: {order_id}")
            return order

    def open_orders(self) -> Iterable[Order]:
        with self._lock:
            return [order for order in self._orders.values() if order.is_active]

    def get_positions(self) -> List[dict]:
        aggregates: Dict[str, Dict[str, float]] = {}
        with self._lock:
            orders = list(self._orders.values())
        for order in orders:
            if order.filled_quantity <= 0:
                continue
            data = aggregates.setdefault(
                order.symbol,
                {
                    "long_qty": 0.0,
                    "long_cost": 0.0,
                    "short_qty": 0.0,
                    "short_cost": 0.0,
                },
            )
            effective_price = (
                order.average_price if order.average_price is not None else order.price
            )
            if order.side is OrderSide.BUY:
                data["long_qty"] += order.filled_quantity
                if effective_price is not None:
                    data["long_cost"] += effective_price * order.filled_quantity
            else:
                data["short_qty"] += order.filled_quantity
                if effective_price is not None:
                    data["short_cost"] += effective_price * order.filled_quantity

        positions: List[dict] = []
        for symbol, data in aggregates.items():
            if data["long_qty"] <= 0 and data["short_qty"] <= 0:
                continue
            position = {
                "symbol": symbol,
                "net_quantity": data["long_qty"] - data["short_qty"],
            }
            if data["long_qty"] > 0:
                position["long_quantity"] = data["long_qty"]
                if data["long_cost"] > 0:
                    position["long_average_price"] = (
                        data["long_cost"] / data["long_qty"]
                    )
            if data["short_qty"] > 0:
                position["short_quantity"] = data["short_qty"]
                if data["short_cost"] > 0:
                    position["short_average_price"] = (
                        data["short_cost"] / data["short_qty"]
                    )
            positions.append(position)
        return positions

    def cancel_replace_order(
        self,
        order_id: str,
        new_order: Order,
        *,
        idempotency_key: str | None = None,
    ) -> Order:
        """Sequential cancel/replace fallback suitable for sandbox usage."""

        if not self.cancel_order(order_id):
            raise OrderError(f"Unknown order_id: {order_id}")
        return self.place_order(new_order, idempotency_key=idempotency_key)


class SimulatedExchangeConnector(ExecutionConnector):
    """Base class providing deterministic sandbox behaviour."""

    def __init__(
        self,
        *,
        sandbox: bool = True,
        symbol_map: Mapping[str, str] | None = None,
        specifications: Mapping[str, SymbolSpecification] | None = None,
        failure_plan: Iterable[Exception | str] | None = None,
    ) -> None:
        super().__init__(sandbox=sandbox)
        self.normalizer = SymbolNormalizer(symbol_map, specifications)
        self._orders: Dict[str, Order] = {}
        self._next_id = 1
        self._idempotency_cache: Dict[str, Order] = {}
        self._failures: Deque[Exception | str] = deque(failure_plan or [])

    def _generate_id(self) -> str:
        order_id = f"{self.__class__.__name__}-{self._next_id:08d}"
        self._next_id += 1
        return order_id

    def _maybe_raise_failure(self) -> None:
        if not self._failures:
            return
        outcome = self._failures.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        mapping = {
            "timeout": TimeoutError("simulated timeout"),
            "network": TransientOrderError("simulated network interruption"),
            "429": TransientOrderError("HTTP 429: rate limited"),
        }
        if outcome in mapping:
            raise mapping[outcome]
        raise ValueError(f"Unknown failure token: {outcome}")

    def schedule_failures(self, *failures: Exception | str) -> None:
        """Queue failures to be raised on subsequent submissions."""

        self._failures.extend(failures)

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        if idempotency_key is not None and idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]

        self._maybe_raise_failure()
        quantity = self.normalizer.round_quantity(order.symbol, order.quantity)
        price = order.price
        if price is not None:
            price = self.normalizer.round_price(order.symbol, price)
        try:
            self.normalizer.validate(order.symbol, quantity, price)
        except NormalizationError as exc:  # pragma: no cover - defensive guard
            raise OrderError(str(exc)) from exc
        normalized_order = replace(order, quantity=quantity, price=price)
        order_id = self._generate_id()
        normalized_order.mark_submitted(order_id)
        self._orders[order_id] = normalized_order
        if idempotency_key is not None:
            self._idempotency_cache[idempotency_key] = normalized_order
        return normalized_order

    def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order is None:
            return False
        order.cancel()
        return True

    def fetch_order(self, order_id: str) -> Order:
        if order_id not in self._orders:
            raise OrderError(f"Unknown order_id: {order_id}")
        return self._orders[order_id]

    def open_orders(self) -> Iterable[Order]:
        return [order for order in self._orders.values() if order.is_active]

    def get_positions(self) -> List[dict]:
        return []

    def apply_fill(self, order_id: str, quantity: float, price: float) -> Order:
        order = self.fetch_order(order_id)
        order.record_fill(quantity, price)
        return order

    def cancel_replace_order(
        self,
        order_id: str,
        new_order: Order,
        *,
        idempotency_key: str | None = None,
    ) -> Order:
        """Sandbox implementation performing cancel/replace sequentially."""

        if not self.cancel_order(order_id):
            raise OrderError(f"Unknown order_id: {order_id}")
        return self.place_order(new_order, idempotency_key=idempotency_key)


class BinanceConnector(SimulatedExchangeConnector):
    def __init__(
        self,
        *,
        sandbox: bool = True,
        failure_plan: Iterable[Exception | str] | None = None,
    ) -> None:
        specs = {
            "BTCUSDT": SymbolSpecification(
                "BTCUSDT",
                min_qty=0.0001,
                min_notional=10,
                step_size=0.0001,
                tick_size=0.1,
            ),
            "ETHUSDT": SymbolSpecification(
                "ETHUSDT",
                min_qty=0.001,
                min_notional=5,
                step_size=0.001,
                tick_size=0.01,
            ),
        }
        super().__init__(
            sandbox=sandbox,
            symbol_map={"BTCUSDT": "BTCUSDT"},
            specifications=specs,
            failure_plan=failure_plan,
        )


class BybitConnector(SimulatedExchangeConnector):
    def __init__(
        self,
        *,
        sandbox: bool = True,
        failure_plan: Iterable[Exception | str] | None = None,
    ) -> None:
        specs = {
            "BTCUSDT": SymbolSpecification(
                "BTCUSDT", min_qty=0.001, min_notional=5, step_size=0.001, tick_size=0.5
            ),
        }
        super().__init__(
            sandbox=sandbox,
            symbol_map={"BTCUSDT": "BTCUSDT"},
            specifications=specs,
            failure_plan=failure_plan,
        )


class KrakenConnector(SimulatedExchangeConnector):
    def __init__(
        self,
        *,
        sandbox: bool = True,
        failure_plan: Iterable[Exception | str] | None = None,
    ) -> None:
        symbol_map = {"BTCUSD": "XBTUSD"}
        specs = {
            "XBTUSD": SymbolSpecification(
                "XBTUSD",
                min_qty=0.0001,
                min_notional=5,
                step_size=0.0001,
                tick_size=0.5,
            ),
        }
        super().__init__(
            sandbox=sandbox,
            symbol_map=symbol_map,
            specifications=specs,
            failure_plan=failure_plan,
        )


class CoinbaseConnector(SimulatedExchangeConnector):
    def __init__(
        self,
        *,
        sandbox: bool = True,
        failure_plan: Iterable[Exception | str] | None = None,
    ) -> None:
        symbol_map = {"BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD"}
        specs = {
            "BTC-USD": SymbolSpecification(
                "BTC-USD",
                min_qty=0.0001,
                min_notional=10,
                step_size=0.0001,
                tick_size=0.01,
            ),
            "ETH-USD": SymbolSpecification(
                "ETH-USD",
                min_qty=0.001,
                min_notional=5,
                step_size=0.001,
                tick_size=0.01,
            ),
        }
        super().__init__(
            sandbox=sandbox,
            symbol_map=symbol_map,
            specifications=specs,
            failure_plan=failure_plan,
        )


__all__ = [
    "OrderError",
    "TransientOrderError",
    "ExecutionConnector",
    "SimulatedExchangeConnector",
    "BinanceConnector",
    "BybitConnector",
    "KrakenConnector",
    "CoinbaseConnector",
    "BinanceRESTConnector",
    "CoinbaseRESTConnector",
]
