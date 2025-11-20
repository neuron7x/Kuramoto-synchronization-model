from __future__ import annotations

import heapq
import random
import threading
import time
from collections.abc import Iterable
from typing import Any, Dict, List, Tuple

from domain import Order
from execution.connectors import ExecutionConnector, TransientOrderError


class FakeExchangeAdapter(ExecutionConnector):
    """Deterministic sandbox exchange adapter for integration tests.

    The adapter extends :class:`execution.connectors.ExecutionConnector` to
    provide reproducible latency, jitter, and failure injection suitable for
    replay-style simulations. Orders are acknowledged synchronously and filled
    asynchronously by a background worker that respects configured latency
    bounds. Fill events are recorded for downstream assertions and debugging.
    """

    def __init__(
        self,
        latency_ms: float = 10.0,
        jitter_ms: float = 5.0,
        fail_rate: float = 0.0,
        disconnect_rate: float = 0.0,
        *,
        symbol: str | None = None,
        seed: int | None = None,
    ) -> None:
        super().__init__(sandbox=True)
        self.latency_ms = max(float(latency_ms), 0.0)
        self.jitter_ms = max(float(jitter_ms), 0.0)
        self.fail_rate = min(max(float(fail_rate), 0.0), 1.0)
        self.disconnect_rate = min(max(float(disconnect_rate), 0.0), 1.0)
        self.symbol = symbol
        self._rng = random.Random(seed)
        self._stop_event = threading.Event()
        self._event_cv = threading.Condition()
        self._event_queue: List[Tuple[float, str]] = []
        self._worker: threading.Thread | None = None
        self._fills: List[Dict[str, Any]] = []
        self._scheduled: set[str] = set()
        self._attempts: Dict[str, int] = {}
        self._fill_cursor = 0

    # ------------------------------------------------------------------
    # Lifecycle
    def connect(self, credentials: Dict[str, str] | None = None) -> None:  # type: ignore[override]
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._event_loop,
            name="fake-exchange-events",
            daemon=True,
        )
        self._worker.start()

    def disconnect(self) -> None:  # type: ignore[override]
        self._stop_event.set()
        with self._event_cv:
            self._event_cv.notify_all()
        if self._worker is not None:
            self._worker.join(timeout=1.0)
            self._worker = None
        self._scheduled.clear()
        self._attempts.clear()
        super().disconnect()

    # ------------------------------------------------------------------
    # Order lifecycle
    def place_order(
        self, order: Order, *, idempotency_key: str | None = None
    ) -> Order:  # type: ignore[override]
        attempt_key = None
        if idempotency_key is not None:
            attempt_key = str(idempotency_key)
            attempts = self._attempts.get(attempt_key, 0)
            if attempts == 0 and self._rng.random() < self.fail_rate:
                self._attempts[attempt_key] = attempts + 1
                raise TransientOrderError("Simulated exchange send failure")
            self._attempts[attempt_key] = attempts + 1

        latency = self._compute_latency_seconds()
        if latency > 0:
            time.sleep(latency)

        submitted = super().place_order(order, idempotency_key=idempotency_key)
        order_id = submitted.order_id
        if order_id is None:
            raise RuntimeError("FakeExchangeAdapter requires orders with IDs")
        if order_id not in self._scheduled:
            self._scheduled.add(order_id)
            self._enqueue_fill(order_id, submitted)
        return submitted

    def fetch_order(self, order_id: str) -> Order:  # type: ignore[override]
        if self.disconnect_rate > 0.0 and self._rng.random() < self.disconnect_rate:
            raise ConnectionError("Simulated exchange disconnection")
        return super().fetch_order(order_id)

    def open_orders(self) -> Iterable[Order]:  # type: ignore[override]
        if self.disconnect_rate > 0.0 and self._rng.random() < self.disconnect_rate:
            raise ConnectionError("Simulated exchange disconnection")
        return super().open_orders()

    # ------------------------------------------------------------------
    # Introspection helpers
    @property
    def fills(self) -> list[dict[str, Any]]:
        """Return a shallow copy of recorded fill events."""

        with self._lock:
            return [dict(event) for event in self._fills]

    def drain_fills(self) -> list[dict[str, Any]]:
        """Return new fill events since the previous drain."""

        with self._lock:
            if self._fill_cursor >= len(self._fills):
                return []
            new_events = [dict(event) for event in self._fills[self._fill_cursor :]]
            self._fill_cursor = len(self._fills)
            return new_events

    # ------------------------------------------------------------------
    # Internal helpers
    def _compute_latency_seconds(self) -> float:
        jitter = 0.0
        if self.jitter_ms > 0.0:
            jitter = self._rng.uniform(-self.jitter_ms, self.jitter_ms)
        latency_ms = max(0.0, self.latency_ms + jitter)
        return latency_ms / 1000.0

    def _enqueue_fill(self, order_id: str, order: Order) -> None:
        execute_at = time.monotonic() + self._compute_latency_seconds()
        with self._event_cv:
            heapq.heappush(self._event_queue, (execute_at, order_id))
            self._event_cv.notify_all()

    def _event_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._event_cv:
                while not self._event_queue and not self._stop_event.is_set():
                    self._event_cv.wait(timeout=0.1)
                if self._stop_event.is_set():
                    return
                execute_at, order_id = heapq.heappop(self._event_queue)
            now = time.monotonic()
            delay = max(0.0, execute_at - now)
            if self._stop_event.wait(delay):
                return
            self._complete_fill(order_id)

    def _complete_fill(self, order_id: str) -> None:
        with self._lock:
            order = self._orders.get(order_id)
            if order is None or not order.is_active:
                return
            remaining = max(order.quantity - order.filled_quantity, 0.0)
            if remaining <= 0:
                return
            price = float(order.price or 1.0)
            order.record_fill(remaining, price)
            self._fills.append(
                {
                    "order_id": order_id,
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "quantity": remaining,
                    "price": price,
                    "timestamp": time.time(),
                }
            )
            if order_id in self._scheduled and not order.is_active:
                self._scheduled.discard(order_id)


__all__ = ["FakeExchangeAdapter"]
