# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Foundational primitives for authenticated REST/WebSocket connectors."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import (
    Any,
    AsyncContextManager,
    Callable,
    Deque,
    Dict,
    Mapping,
    MutableMapping,
)

import httpx

from domain import Order
from execution.connectors import ExecutionConnector, OrderError, TransientOrderError
from execution.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
)


def _first_present(payload: Mapping[str, Any], *keys: str) -> Any:
    """Return the first value found for ``keys`` in ``payload``.

    The lookup preserves falsy but meaningful values such as ``0`` while
    treating absent keys uniformly.  The function is intentionally tolerant of
    non-mapping payloads because the execution adapters routinely deal with
    partially structured API responses.
    """

    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _coerce_optional_float(value: Any) -> float | None:
    """Best-effort conversion of arbitrary payload values into ``float``.

    Values that cannot be interpreted as numeric inputs (including booleans,
    blank strings, nested structures, etc.) yield ``None`` instead of raising.
    This makes downstream parsing logic resilient to schema drift and malformed
    exchange responses uncovered by fuzz/property tests.
    """

    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return float(candidate)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any, *, default: float) -> float:
    """Return ``value`` converted to ``float`` or ``default`` on failure."""

    parsed = _coerce_optional_float(value)
    if parsed is None:
        return default
    return parsed


class SlidingWindowRateLimiter:
    """Simple sliding-window rate limiter with blocking semantics."""

    def __init__(
        self,
        *,
        max_requests: int,
        interval_seconds: float,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._max_requests = max_requests
        self._interval = interval_seconds
        self._clock = clock or time.monotonic
        self._events: Deque[tuple[float, int]] = deque()
        self._in_window = 0
        self._lock = threading.Lock()

    def acquire(self, weight: int = 1) -> None:
        if weight <= 0:
            return
        backoff = 0.0
        while True:
            with self._lock:
                now = self._clock()
                while self._events and now - self._events[0][0] >= self._interval:
                    _, event_weight = self._events.popleft()
                    self._in_window = max(0, self._in_window - event_weight)
                if self._in_window + weight <= self._max_requests:
                    self._events.append((now, weight))
                    self._in_window += weight
                    return
                oldest_time, _ = self._events[0]
                backoff = max(0.0, self._interval - (now - oldest_time))
            time.sleep(min(backoff, 0.5) if backoff else 0.01)


class RESTWebSocketConnector(ExecutionConnector, ABC):
    """Base class combining REST interactions with WebSocket streaming."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        sandbox: bool,
        http_client: httpx.Client | None = None,
        ws_factory: Callable[[str], AsyncContextManager[Any]] | None = None,
        rate_limit: tuple[int, float] = (1200, 60.0),
        max_backoff: float = 30.0,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
    ) -> None:
        super().__init__(sandbox=sandbox)
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._logger = logging.getLogger(f"execution.connector.{name}")
        self._http_client = http_client
        self._owns_client = http_client is None
        self._ws_factory = ws_factory or self._default_ws_factory
        self._rate_limiter = SlidingWindowRateLimiter(
            max_requests=max(rate_limit[0], 1), interval_seconds=max(rate_limit[1], 0.1)
        )
        self._max_backoff = max(1.0, float(max_backoff))
        self._circuit_breaker = CircuitBreaker(circuit_breaker_config or CircuitBreakerConfig())
        self._ws_stop = threading.Event()
        self._ws_thread: threading.Thread | None = None
        self._orders: MutableMapping[str, Order] = {}
        self._idempotency_cache: Dict[str, Order] = {}
        self._lock = threading.Lock()
        self._connected = False
        self._credentials: Mapping[str, str] = {}

    # ------------------------------------------------------------------
    # Abstract hooks for subclasses
    @abstractmethod
    def _resolve_credentials(self, credentials: Mapping[str, str] | None) -> Mapping[str, str]:
        """Normalise credentials supplied either programmatically or via env."""

    @abstractmethod
    def _sign_request(
        self,
        method: str,
        path: str,
        *,
        params: Dict[str, Any],
        json_payload: Dict[str, Any] | None,
        headers: Dict[str, str],
    ) -> tuple[Dict[str, Any], Dict[str, Any] | None, Dict[str, str], Any | None]:
        """Return request components with venue-specific authentication applied."""

    @abstractmethod
    def _order_endpoint(self) -> str:
        """Endpoint used for order submission requests."""

    @abstractmethod
    def _build_place_payload(self, order: Order, idempotency_key: str | None) -> Dict[str, Any]:
        """Serialise an :class:`Order` into the venue's REST payload format."""

    @abstractmethod
    def _parse_order(self, payload: Mapping[str, Any], *, original: Order | None = None) -> Order:
        """Convert REST/WS payloads back into :class:`Order` objects."""

    @abstractmethod
    def _cancel_endpoint(self, order_id: str) -> tuple[str, Dict[str, Any]]:
        """Return endpoint and params for cancelling ``order_id``."""

    @abstractmethod
    def _fetch_endpoint(self, order_id: str) -> tuple[str, Dict[str, Any]]:
        """Return endpoint and params for fetching ``order_id``."""

    @abstractmethod
    def _open_orders_endpoint(self) -> tuple[str, Dict[str, Any]]:
        """Return endpoint and params for listing open orders."""

    @abstractmethod
    def _positions_endpoint(self) -> tuple[str, Dict[str, Any]]:
        """Return endpoint and params for retrieving positions."""

    @abstractmethod
    def _parse_positions(self, payload: Mapping[str, Any] | list[Any]) -> list[dict]:
        """Normalise venue-specific position payloads into dictionaries."""

    def _stream_url(self) -> str | None:
        return None

    @abstractmethod
    def _handle_stream_message(self, payload: Mapping[str, Any]) -> None:
        """Process a WebSocket payload emitted by the venue."""

    def _default_headers(self) -> Dict[str, str]:
        return {}

    # ------------------------------------------------------------------
    # Public interface
    def connect(self, credentials: Mapping[str, str] | None = None) -> None:
        if self._connected:
            return
        resolved = self._resolve_credentials(credentials)
        if self._http_client is None:
            self._http_client = httpx.Client(
                base_url=self._base_url, timeout=httpx.Timeout(10.0, read=30.0)
            )
        self._credentials = resolved
        self._connected = True
        stream_url = self._stream_url()
        if stream_url:
            self._start_stream(stream_url)

    def disconnect(self) -> None:
        self._ws_stop.set()
        thread = self._ws_thread
        if thread is not None:
            thread.join(timeout=5.0)
            self._ws_thread = None
        if self._owns_client and self._http_client is not None:
            self._http_client.close()
            self._http_client = None
        self._connected = False

    # ------------------------------------------------------------------
    # REST helpers
    def _weight_for(self, method: str, path: str) -> int:
        """Return the request weight for rate limiting purposes."""

        return 1

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Dict[str, Any] | None = None,
        json_payload: Dict[str, Any] | None = None,
        signed: bool = False,
        weight: int | None = None,
    ) -> Mapping[str, Any] | list:
        if not self._connected or self._http_client is None:
            raise RuntimeError("Connector is not connected")

        # Check circuit breaker before allowing request
        if not self._circuit_breaker.allow_request():
            state = self._circuit_breaker.state
            ttl = self._circuit_breaker.get_time_until_recovery()
            reason = self._circuit_breaker.get_last_trip_reason() or "repeated failures"
            self._logger.warning(
                "Circuit breaker blocked request",
                extra={
                    "state": state.value,
                    "recovery_seconds": ttl,
                    "reason": reason,
                },
            )
            raise TransientOrderError(f"Circuit breaker {state.value} - service unavailable")

        request_weight = weight if weight is not None else self._weight_for(method, path)
        self._rate_limiter.acquire(max(1, int(request_weight)))
        request_params = dict(params or {})
        request_json = dict(json_payload) if json_payload is not None else None
        headers = self._default_headers()
        data_payload: Any | None = None
        if signed:
            (
                request_params,
                request_json,
                headers,
                data_payload,
            ) = self._sign_request(
                method,
                path,
                params=request_params,
                json_payload=request_json,
                headers=headers,
            )
        try:
            response = self._http_client.request(
                method,
                path,
                params=request_params,
                json=request_json,
                data=data_payload,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            self._circuit_breaker.record_failure()
            self._logger.error(
                "HTTP request timed out",
                extra={"method": method, "path": path},
            )
            raise TransientOrderError("HTTP request timed out") from exc
        except httpx.RequestError as exc:
            self._circuit_breaker.record_failure()
            message = str(exc)
            if not message:
                message = exc.__class__.__name__
            self._logger.error(
                "HTTP request failed",
                extra={"method": method, "path": path, "error": message},
            )
            raise TransientOrderError(f"HTTP request failed: {message}") from exc

        # Record success/failure based on response status
        if response.status_code == 429:
            self._circuit_breaker.record_failure()
            raise TransientOrderError("HTTP 429: rate limited")
        if 500 <= response.status_code < 600:
            self._circuit_breaker.record_failure()
            raise TransientOrderError(f"HTTP {response.status_code}: transient server error")
        if response.is_error:
            self._circuit_breaker.record_failure()
            raise OrderError(f"HTTP {response.status_code}: {response.text}")

        # Success case
        self._circuit_breaker.record_success()

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise OrderError("Invalid JSON response from exchange") from exc
        if not isinstance(payload, (Mapping, list)):
            raise OrderError("Unexpected response payload type")
        return payload

    # ------------------------------------------------------------------
    # ExecutionConnector API
    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        if idempotency_key and idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]
        payload = self._build_place_payload(order, idempotency_key)
        response = self._request("POST", self._order_endpoint(), params=payload, signed=True)
        submitted = self._parse_order(response, original=order)
        with self._lock:
            self._orders[submitted.order_id or ""] = submitted
            if idempotency_key:
                self._idempotency_cache[idempotency_key] = submitted
        return submitted

    def cancel_order(self, order_id: str) -> bool:
        path, payload = self._cancel_endpoint(order_id)
        self._request("DELETE", path, params=payload, signed=True)
        with self._lock:
            if order_id in self._orders:
                self._orders[order_id].cancel()
        return True

    def fetch_order(self, order_id: str) -> Order:
        path, payload = self._fetch_endpoint(order_id)
        response = self._request("GET", path, params=payload, signed=True)
        order = self._parse_order(response)
        with self._lock:
            self._orders[order.order_id or order_id] = order
        return order

    def open_orders(self) -> list[Order]:
        path, payload = self._open_orders_endpoint()
        response = self._request("GET", path, params=payload, signed=True)
        orders_payload = response.get("orders") if "orders" in response else response
        if isinstance(orders_payload, Mapping):
            values = list(orders_payload.values())
        else:
            values = list(orders_payload) if isinstance(orders_payload, list) else []
        orders: list[Order] = []
        for item in values:
            if not isinstance(item, Mapping):
                continue
            orders.append(self._parse_order(item))
        with self._lock:
            for order in orders:
                if order.order_id:
                    self._orders[order.order_id] = order
        return orders

    def get_positions(self) -> list[dict]:
        path, payload = self._positions_endpoint()
        response = self._request("GET", path, params=payload, signed=True)
        return self._parse_positions(response)

    def cancel_replace_order(
        self,
        order_id: str,
        new_order: Order,
        *,
        idempotency_key: str | None = None,
    ) -> Order:
        raise OrderError("Cancel/replace is not supported by this connector")

    # ------------------------------------------------------------------
    # Circuit breaker and health monitoring
    def get_circuit_breaker_state(self) -> CircuitBreakerState:
        """Return the current circuit breaker state.

        Returns:
            CircuitBreakerState: Current state (CLOSED, OPEN, or HALF_OPEN).
        """
        return self._circuit_breaker.state

    def get_circuit_breaker_metrics(self) -> Dict[str, Any]:
        """Return circuit breaker health metrics.

        Returns:
            Dict containing state, failure rate, and recovery information.
        """
        return {
            "state": self._circuit_breaker.state.value,
            "failure_rate": self._circuit_breaker.failure_rate(),
            "time_until_recovery": self._circuit_breaker.get_time_until_recovery(),
            "last_trip_reason": self._circuit_breaker.get_last_trip_reason(),
        }

    def reset_circuit_breaker(self) -> None:
        """Manually reset circuit breaker to closed state.

        Should only be used for administrative purposes or testing.
        """
        self._circuit_breaker.reset()
        self._logger.info("Circuit breaker manually reset to CLOSED state")

    # ------------------------------------------------------------------
    # Streaming helpers
    def _start_stream(self, url: str) -> None:
        self._ws_stop.clear()
        self._ws_thread = threading.Thread(
            target=self._run_stream_loop,
            args=(url,),
            name=f"{self.name}-ws",
            daemon=True,
        )
        self._ws_thread.start()

    @staticmethod
    def _default_ws_factory(url: str) -> AsyncContextManager[Any]:
        if not url:
            raise RuntimeError("WebSocket URL is required for streaming support")
        try:
            from websockets.asyncio.client import connect
        except Exception as exc:  # pragma: no cover - optional dependency guard
            raise RuntimeError("websockets>=15.0 is required for market data streaming") from exc
        return connect(
            url,
            ping_interval=20.0,
            ping_timeout=20.0,
            close_timeout=5.0,
            max_size=2**20,
        )

    def _run_stream_loop(self, url: str) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._consume_stream(url))
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()

    async def _consume_stream(self, url: str) -> None:
        backoff = 1.0
        attempt = 0
        while not self._ws_stop.is_set():
            try:
                async with self._ws_factory(url) as websocket:
                    attempt = 0
                    backoff = 1.0
                    while not self._ws_stop.is_set():
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue
                        except Exception as exc:  # pragma: no cover - defensive
                            self._logger.warning(
                                "WebSocket receive failed", extra={"error": str(exc)}
                            )
                            break
                        if message is None:
                            continue
                        try:
                            payload = json.loads(message)
                        except json.JSONDecodeError:
                            self._logger.debug("Ignoring non-JSON message from stream")
                            continue
                        if isinstance(payload, Mapping):
                            self._handle_stream_message(payload)
            except Exception as exc:
                attempt += 1
                delay = min(self._max_backoff, backoff * (2 ** max(0, attempt - 1)))
                self._logger.warning(
                    "WebSocket connection failed",
                    extra={"attempt": attempt, "delay": delay, "error": str(exc)},
                )
                try:
                    await asyncio.wait_for(asyncio.sleep(delay), timeout=delay)
                except asyncio.TimeoutError:
                    pass
        self._logger.debug("WebSocket loop exiting")


__all__ = ["RESTWebSocketConnector", "SlidingWindowRateLimiter"]
