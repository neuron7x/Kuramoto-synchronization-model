"""Microservice wrapping order execution flows."""

from __future__ import annotations

import time
from typing import MutableMapping

from application.microservices.base import Microservice, ServiceState
from application.microservices.contracts import (
    ExecutionRequest,
    IntegrationContractRegistry,
    default_contract_registry,
)
from application.system import TradePulseSystem
from core.messaging.idempotency import InMemoryEventIdempotencyStore
from domain import Order
from execution.live_loop import LiveExecutionLoop


class ExecutionService(Microservice):
    """Expose order submission and live loop lifecycle via a dedicated service."""

    def __init__(
        self,
        system: TradePulseSystem,
        *,
        contracts: IntegrationContractRegistry | None = None,
        idempotency_ttl_seconds: int = 3600,
    ) -> None:
        super().__init__(name="execution")
        self._system = system
        self._last_order: Order | None = None
        self._contracts = contracts or default_contract_registry()
        try:
            self._operation_contracts["submit"] = self._contracts.get_service(
                "tradepulse.service.execution.submit"
            )
            self._operation_contracts["ensure_live_loop"] = self._contracts.get_service(
                "tradepulse.service.execution.ensure_live_loop"
            )
        except KeyError:  # pragma: no cover - defensive
            pass
        self._idempotency_store = InMemoryEventIdempotencyStore(
            ttl_seconds=idempotency_ttl_seconds
        )
        self._replay_cache: MutableMapping[str, tuple[Order, float]] = {}
        self._idempotency_ttl = float(idempotency_ttl_seconds)

    def submit(self, request: ExecutionRequest) -> Order:
        """Submit a signal for execution and return the resulting order."""

        self._ensure_active()
        contract = self._operation_contract("submit")
        attributes = {"venue": request.venue, "symbol": request.signal.symbol}
        if contract and contract.observability:
            attributes = contract.observability.attributes(attributes)
        idempotency_key = request.idempotency_key or request.correlation_id
        with self._operation_context("submit", attributes=attributes):
            now = time.monotonic()
            if idempotency_key:
                self._purge_stale_replays(now)
                replay = self._replay_cache.get(idempotency_key)
                if replay is not None:
                    order, stored_at = replay
                    if (
                        now - stored_at <= self._idempotency_ttl
                        and self._idempotency_store.was_processed(idempotency_key)
                    ):
                        self._mark_idempotent_replay("submit")
                        self._last_order = order
                        self._mark_healthy()
                        return order
                    self._replay_cache.pop(idempotency_key, None)
            try:
                order = self._execute_with_retries(
                    lambda: self._system.submit_signal(
                        request.signal,
                        venue=request.venue,
                        quantity=request.quantity,
                        price=request.price,
                        order_type=request.order_type,
                        correlation_id=request.correlation_id,
                    ),
                    contract.retry_policy if contract else None,
                )
            except Exception as exc:
                self._mark_error(exc)
                raise
            else:
                if idempotency_key:
                    self._idempotency_store.mark_processed(idempotency_key)
                    self._replay_cache[idempotency_key] = (order, time.monotonic())
                self._last_order = order
                self._mark_healthy()
                return order

    def ensure_live_loop(self) -> LiveExecutionLoop:
        """Ensure the live execution loop has been initialised."""

        self._ensure_active()
        contract = self._operation_contract("ensure_live_loop")
        attributes = {"connectors": len(self._system.connector_names)}
        if contract and contract.observability:
            attributes = contract.observability.attributes(attributes)
        with self._operation_context("ensure_live_loop", attributes=attributes):
            try:
                loop = self._execute_with_retries(
                    self._system.ensure_live_loop,
                    contract.retry_policy if contract else None,
                )
            except Exception as exc:
                self._mark_error(exc)
                raise
            else:
                self._mark_healthy()
                return loop

    def _health_metadata(self) -> dict[str, object] | None:
        if self.state is ServiceState.STOPPED:
            return None
        metadata: dict[str, object] = {}
        if self._last_order is not None:
            metadata["last_symbol"] = self._last_order.symbol
            metadata["last_quantity"] = self._last_order.quantity
            metadata["last_side"] = self._last_order.side.value
        if self.last_error is not None:
            metadata["last_error"] = self.last_error
        metadata["idempotency"] = {
            "entries": len(self._replay_cache),
            "ttl_seconds": int(self._idempotency_ttl),
        }
        return metadata or None

    def _purge_stale_replays(self, now: float | None = None) -> None:
        if now is None:
            now = time.monotonic()
        ttl = self._idempotency_ttl
        for key, (_, stored_at) in list(self._replay_cache.items()):
            if now - stored_at > ttl:
                self._replay_cache.pop(key, None)


__all__ = ["ExecutionService"]
