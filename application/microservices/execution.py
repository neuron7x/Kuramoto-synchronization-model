"""Microservice wrapping order execution flows."""

from __future__ import annotations

from application.microservices.base import Microservice, ServiceState
from application.microservices.contracts import ExecutionRequest
from application.system import TradePulseSystem
from domain import Order
from execution.live_loop import LiveExecutionLoop


class ExecutionService(Microservice):
    """Expose order submission and live loop lifecycle via a dedicated service."""

    def __init__(self, system: TradePulseSystem) -> None:
        super().__init__(name="execution")
        self._system = system
        self._last_order: Order | None = None

    def submit(self, request: ExecutionRequest) -> Order:
        """Submit a signal for execution and return the resulting order."""

        self._ensure_active()
        try:
            order = self._system.submit_signal(
                request.signal,
                venue=request.venue,
                quantity=request.quantity,
                price=request.price,
                order_type=request.order_type,
                correlation_id=request.correlation_id,
            )
        except Exception as exc:
            self._mark_error(exc)
            raise
        else:
            self._last_order = order
            self._mark_healthy()
            return order

    def ensure_live_loop(self) -> LiveExecutionLoop:
        """Ensure the live execution loop has been initialised."""

        self._ensure_active()
        try:
            loop = self._system.ensure_live_loop()
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
        return metadata or None


__all__ = ["ExecutionService"]
