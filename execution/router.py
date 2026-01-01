# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Resilient execution routing across multiple broker/exchange connectors.

The module coordinates :class:`~execution.connectors.ExecutionConnector`
implementations, layering venue specific normalisation, resilience primitives
and portfolio aware routing decisions.  The router is designed for EMS use
cases where TradePulse needs to balance fast failover with deterministic
behaviour in sandbox environments.
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Callable, Dict, Iterable, Mapping, MutableMapping

from domain import Order, OrderSide, OrderStatus, OrderType

from .connectors import ExecutionConnector, OrderError, TransientOrderError
from .resilience.circuit_breaker import ExchangeResilienceProfile


@dataclass(slots=True, frozen=True)
class NormalizedOrderState:
    """Venue-agnostic view of an order's lifecycle state."""

    status: OrderStatus
    filled_quantity: float
    average_price: float | None = None
    rejection_reason: str | None = None


@dataclass(slots=True)
class OrderStateNormalizer:
    """Convert venue specific payloads into :class:`NormalizedOrderState`."""

    status_overrides: Mapping[str, OrderStatus] = field(default_factory=dict)

    def normalize(self, order: Order) -> NormalizedOrderState:
        status = order.status
        if order.order_id and order.order_id in self.status_overrides:
            status = self.status_overrides[order.order_id]
        return NormalizedOrderState(
            status=status,
            filled_quantity=order.filled_quantity,
            average_price=order.average_price,
            rejection_reason=order.rejection_reason,
        )


@dataclass(slots=True)
class ErrorMapper:
    """Translate raw venue errors into canonical :class:`OrderError` types."""

    mapping: Mapping[str, type[OrderError]] = field(default_factory=dict)

    def translate(self, error: Exception) -> Exception:
        message = str(error)
        for token, exc_type in self.mapping.items():
            if token in message:
                return exc_type(message)
        return error


@dataclass(slots=True)
class SlippageModel:
    """Apply deterministic slippage and limit buffers when routing orders."""

    max_slippage_bps: float = 5.0
    limit_buffer_bps: float = 10.0

    def apply(self, order: Order) -> Order:
        adjusted = replace(order)
        if order.order_type is OrderType.MARKET:
            return adjusted

        price = order.price
        if price is None or price <= 0:
            return adjusted

        direction = 1 if order.side is OrderSide.BUY else -1
        buffer = price * (self.limit_buffer_bps / 10_000.0)
        slippage = price * (self.max_slippage_bps / 10_000.0)

        if direction > 0:
            adjusted.price = price + buffer + slippage
        else:
            adjusted.price = max(1e-8, price - buffer - slippage)
        return adjusted


@dataclass(slots=True)
class ExecutionRoute:
    """Represents a trading route with associated resilience profile."""

    name: str
    connector: ExecutionConnector
    resilience: ExchangeResilienceProfile
    normalizer: OrderStateNormalizer = field(default_factory=OrderStateNormalizer)
    slippage_model: SlippageModel | None = None
    error_mapper: ErrorMapper = field(default_factory=ErrorMapper)
    operation_timeout: float | None = 0.75

    def apply_slippage(self, order: Order) -> Order:
        if self.slippage_model is None:
            return order
        return self.slippage_model.apply(order)

    def normalize(self, order: Order) -> NormalizedOrderState:
        return self.normalizer.normalize(order)

    def translate_error(self, error: Exception) -> Exception:
        return self.error_mapper.translate(error)


class ResilientExecutionRouter:
    """Coordinate execution across connectors with failover and safeguards."""

    def __init__(self) -> None:
        self._routes: Dict[str, ExecutionRoute] = {}
        self._failover: Dict[str, str] = {}
        self._idempotency: MutableMapping[str, tuple[str, str]] = {}

    # ------------------------------------------------------------------
    # Registration
    def register_route(
        self,
        name: str,
        primary: ExecutionRoute,
        *,
        backup: ExecutionRoute | None = None,
    ) -> None:
        key = name.lower()
        if key in self._routes:
            raise ValueError(f"Route '{name}' already registered")
        self._routes[key] = primary
        if backup is not None:
            backup_key = f"{key}__backup"
            if backup_key in self._routes:
                raise ValueError(f"Backup route for '{name}' already registered")
            self._routes[backup_key] = backup
            self._failover[key] = backup_key

    # ------------------------------------------------------------------
    # High level helpers
    def _resolve_route(self, name: str) -> tuple[str, ExecutionRoute]:
        key = name.lower()
        if key not in self._routes:
            raise LookupError(f"Unknown execution route '{name}'")
        return key, self._routes[key]

    def _record_result(
        self,
        route_key: str,
        resilience: ExchangeResilienceProfile,
        started_at: float,
        *,
        success: bool,
        error: Exception | None,
    ) -> Exception | None:
        latency_ms = (perf_counter() - started_at) * 1000.0
        resilience.release(success, latency_ms, error)
        if not success and error is not None:
            return self._routes[route_key].translate_error(error)
        return None

    def _execute_with_timeout(
        self,
        route: ExecutionRoute,
        connector: ExecutionConnector,
        func: Callable[[ExecutionRoute, ExecutionConnector], Order],
    ) -> Order:
        timeout = route.operation_timeout
        if not timeout:
            return func(route, connector)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, route, connector)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError as exc:
                future.cancel()
                raise TimeoutError(
                    f"Route '{route.name}' {timeout:.3f}s timeout"
                ) from exc

    def _execute(
        self,
        route_name: str,
        operation: str,
        func: Callable[[ExecutionRoute, ExecutionConnector], Order],
        *,
        idempotency_key: str | None = None,
    ) -> NormalizedOrderState:
        route_key, route = self._resolve_route(route_name)
        connector = route.connector
        resilience = route.resilience

        if not resilience.allow_request():
            raise TransientOrderError(
                f"Route '{route_name}' temporarily throttled by resilience policy"
            )

        started = perf_counter()
        translated: Exception | None = None
        try:
            order = resilience.execute_with_fallback(
                route.name,
                operation,
                self._execute_with_timeout,
                route,
                connector,
                func,
            )
        except Exception as exc:  # noqa: BLE001
            translated = self._record_result(
                route_key,
                resilience,
                started_at=started,
                success=False,
                error=exc,
            )
            failover_key = self._failover.get(route_key)
            if failover_key is None:
                raise (translated or route.translate_error(exc))
            backup = self._routes[failover_key]
            if not backup.resilience.allow_request():
                raise (translated or route.translate_error(exc))
            backup_started = perf_counter()
            try:
                order = backup.resilience.execute_with_fallback(
                    backup.name,
                    operation,
                    self._execute_with_timeout,
                    backup,
                    backup.connector,
                    func,
                )
            except Exception as secondary_exc:  # noqa: BLE001
                secondary_translated = self._record_result(
                    failover_key,
                    backup.resilience,
                    started_at=backup_started,
                    success=False,
                    error=secondary_exc,
                )
                primary_error = translated or route.translate_error(exc)
                secondary_error = secondary_translated or backup.translate_error(
                    secondary_exc
                )
                raise secondary_error from primary_error
            else:
                self._record_result(
                    failover_key,
                    backup.resilience,
                    started_at=backup_started,
                    success=True,
                    error=None,
                )
                if idempotency_key and order.order_id:
                    self._idempotency[idempotency_key] = (failover_key, order.order_id)
                return backup.normalize(order)
        else:
            self._record_result(
                route_key,
                resilience,
                started_at=started,
                success=True,
                error=None,
            )
            if idempotency_key and order.order_id:
                self._idempotency[idempotency_key] = (route_key, order.order_id)
            return route.normalize(order)

    # ------------------------------------------------------------------
    # Public API
    def place_order(
        self,
        route_name: str,
        order: Order,
        *,
        idempotency_key: str | None = None,
    ) -> NormalizedOrderState:
        if idempotency_key is not None:
            existing = self._idempotency.get(idempotency_key)
            if existing is not None:
                stored_route, order_id = existing
                _, route = self._resolve_route(stored_route)
                return route.normalize(route.connector.fetch_order(order_id))

        _, route = self._resolve_route(route_name)

        def _place(
            active_route: ExecutionRoute, connector: ExecutionConnector
        ) -> Order:
            adjusted = active_route.apply_slippage(order)
            return connector.place_order(adjusted, idempotency_key=idempotency_key)

        return self._execute(
            route_name,
            "place_order",
            _place,
            idempotency_key=idempotency_key,
        )

    def cancel_order(self, route_name: str, order_id: str) -> bool:
        route_key, route = self._resolve_route(route_name)
        resilience = route.resilience
        if not resilience.allow_request():
            raise TransientOrderError(
                f"Route '{route_name}' temporarily throttled by resilience policy"
            )

        started = perf_counter()
        error: Exception | None = None
        try:
            result = resilience.execute_with_fallback(
                route.name,
                "cancel_order",
                lambda connector: connector.cancel_order(order_id),
                route.connector,
            )
        except Exception as exc:  # noqa: BLE001
            error = exc
            self._record_result(
                route_key, resilience, started_at=started, success=False, error=exc
            )
            failover_key = self._failover.get(route_key)
            if failover_key is None:
                raise route.translate_error(exc)
            backup = self._routes[failover_key]
            if not backup.resilience.allow_request():
                raise route.translate_error(exc)
            backup_started = perf_counter()
            try:
                result = backup.resilience.execute_with_fallback(
                    backup.name,
                    "cancel_order",
                    lambda connector: connector.cancel_order(order_id),
                    backup.connector,
                )
            except Exception as secondary_exc:  # noqa: BLE001
                self._record_result(
                    failover_key,
                    backup.resilience,
                    started_at=backup_started,
                    success=False,
                    error=secondary_exc,
                )
                raise backup.translate_error(secondary_exc) from route.translate_error(
                    error
                )
            else:
                self._record_result(
                    failover_key,
                    backup.resilience,
                    started_at=backup_started,
                    success=True,
                    error=None,
                )
                return result
        else:
            self._record_result(
                route_key, resilience, started_at=started, success=True, error=None
            )
            return result

    def fetch_order(self, route_name: str, order_id: str) -> NormalizedOrderState:
        _, route = self._resolve_route(route_name)
        order = route.connector.fetch_order(order_id)
        return route.normalize(order)

    def open_orders(self, route_name: str) -> Iterable[NormalizedOrderState]:
        _, route = self._resolve_route(route_name)
        return [route.normalize(order) for order in route.connector.open_orders()]

    def get_positions(self, route_name: str) -> list[dict]:
        _, route = self._resolve_route(route_name)
        return route.connector.get_positions()


__all__ = [
    "ExecutionRoute",
    "ErrorMapper",
    "NormalizedOrderState",
    "OrderStateNormalizer",
    "ResilientExecutionRouter",
    "SlippageModel",
]
