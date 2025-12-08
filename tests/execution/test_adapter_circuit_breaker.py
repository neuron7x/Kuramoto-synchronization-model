"""Tests for circuit breaker integration in exchange adapters."""

from __future__ import annotations

import time
from typing import Any, Mapping

import httpx
import pytest

from domain import Order, OrderSide, OrderType
from execution.adapters.base import RESTWebSocketConnector
from execution.connectors import TransientOrderError
from execution.resilience.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerState,
)


class TestConnector(RESTWebSocketConnector):
    """Test connector for circuit breaker integration tests."""

    def __init__(self, transport: httpx.BaseTransport) -> None:
        super().__init__(
            name="test",
            base_url="https://api.test.com",
            sandbox=True,
            http_client=httpx.Client(
                base_url="https://api.test.com", transport=transport
            ),
            circuit_breaker_config=CircuitBreakerConfig(
                failure_threshold=3,
                recovery_timeout=1.0,
                half_open_max_calls=2,
            ),
        )

    def _resolve_credentials(
        self, credentials: Mapping[str, str] | None
    ) -> Mapping[str, str]:
        return dict(credentials or {})

    def _sign_request(self, method: str, path: str, *, params, json_payload, headers):  # type: ignore[override]
        return params, json_payload, headers, None

    def _order_endpoint(self) -> str:
        return "/order"

    def _build_place_payload(
        self, order: Order, idempotency_key: str | None
    ) -> dict[str, Any]:
        return {
            "symbol": order.symbol,
            "side": order.side.value,
            "type": order.order_type.value,
            "quantity": str(order.quantity),
        }

    def _parse_order(
        self, payload: Mapping[str, Any], *, original: Order | None = None
    ) -> Order:
        return Order(
            symbol=payload.get("symbol", "BTC/USDT"),
            side=OrderSide(payload.get("side", "buy")),
            quantity=float(payload.get("quantity", 1.0)),
            order_type=OrderType(payload.get("type", "market")),
            order_id=payload.get("id", "test-id"),
        )

    def _cancel_endpoint(self, order_id: str) -> tuple[str, dict[str, Any]]:
        return "/order", {"id": order_id}

    def _fetch_endpoint(self, order_id: str) -> tuple[str, dict[str, Any]]:
        return "/order", {"id": order_id}

    def _open_orders_endpoint(self) -> tuple[str, dict[str, Any]]:
        return "/orders", {}

    def _positions_endpoint(self) -> tuple[str, dict[str, Any]]:
        return "/positions", {}

    def _parse_positions(self, payload: Mapping[str, Any] | list[Any]) -> list[dict]:
        return []

    def _handle_stream_message(self, payload: Mapping[str, Any]) -> None:
        pass


class TestCircuitBreakerIntegration:
    """Test suite for circuit breaker integration in adapters."""

    def test_circuit_breaker_initial_state(self) -> None:
        """Test circuit breaker starts in CLOSED state."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"success": True})
        )
        connector = TestConnector(transport)
        connector.connect()

        state = connector.get_circuit_breaker_state()
        assert state == CircuitBreakerState.CLOSED

        connector.disconnect()

    def test_circuit_breaker_opens_on_failures(self) -> None:
        """Test circuit breaker opens after threshold failures."""
        call_count = 0

        def handle_request(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(500, json={"error": "server error"})

        transport = httpx.MockTransport(handle_request)
        connector = TestConnector(transport)
        connector.connect()

        # Trigger failures to open circuit breaker
        for _ in range(3):
            with pytest.raises(TransientOrderError):
                connector._request("GET", "/test")

        state = connector.get_circuit_breaker_state()
        assert state == CircuitBreakerState.OPEN

        connector.disconnect()

    def test_circuit_breaker_blocks_requests_when_open(self) -> None:
        """Test circuit breaker blocks requests when open."""
        call_count = 0

        def handle_request(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(500, json={"error": "server error"})

        transport = httpx.MockTransport(handle_request)
        connector = TestConnector(transport)
        connector.connect()

        # Trigger failures to open circuit breaker
        for _ in range(3):
            with pytest.raises(TransientOrderError):
                connector._request("GET", "/test")

        # Circuit breaker should block further requests
        with pytest.raises(TransientOrderError, match="Circuit breaker"):
            connector._request("GET", "/test")

        # Call count should not increase (request was blocked)
        assert call_count == 3

        connector.disconnect()

    def test_circuit_breaker_transitions_to_half_open(self) -> None:
        """Test circuit breaker transitions to HALF_OPEN after recovery timeout."""
        call_count = 0

        def handle_request(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                return httpx.Response(500, json={"error": "server error"})
            return httpx.Response(200, json={"success": True})

        transport = httpx.MockTransport(handle_request)
        connector = TestConnector(transport)
        connector.connect()

        # Trigger failures
        for _ in range(3):
            with pytest.raises(TransientOrderError):
                connector._request("GET", "/test")

        assert connector.get_circuit_breaker_state() == CircuitBreakerState.OPEN

        # Wait for recovery timeout
        time.sleep(1.1)

        # Next request should attempt and transition to HALF_OPEN
        response = connector._request("GET", "/test")
        assert response == {"success": True}
        assert connector.get_circuit_breaker_state() == CircuitBreakerState.CLOSED

        connector.disconnect()

    def test_circuit_breaker_closes_on_success_in_half_open(self) -> None:
        """Test circuit breaker closes after successful request in HALF_OPEN."""
        call_count = 0

        def handle_request(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                return httpx.Response(500, json={"error": "server error"})
            return httpx.Response(200, json={"success": True})

        transport = httpx.MockTransport(handle_request)
        connector = TestConnector(transport)
        connector.connect()

        # Open circuit breaker
        for _ in range(3):
            with pytest.raises(TransientOrderError):
                connector._request("GET", "/test")

        # Wait for recovery
        time.sleep(1.1)

        # Success should close circuit
        connector._request("GET", "/test")
        assert connector.get_circuit_breaker_state() == CircuitBreakerState.CLOSED

        connector.disconnect()

    def test_circuit_breaker_reopens_on_failure_in_half_open(self) -> None:
        """Test circuit breaker reopens if failure occurs in HALF_OPEN state."""
        call_count = 0

        def handle_request(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(500, json={"error": "server error"})

        transport = httpx.MockTransport(handle_request)
        connector = TestConnector(transport)
        connector.connect()

        # Open circuit breaker
        for _ in range(3):
            with pytest.raises(TransientOrderError):
                connector._request("GET", "/test")

        # Wait for recovery
        time.sleep(1.1)

        # Failure in half-open should reopen circuit
        with pytest.raises(TransientOrderError):
            connector._request("GET", "/test")

        assert connector.get_circuit_breaker_state() == CircuitBreakerState.OPEN

        connector.disconnect()

    def test_circuit_breaker_records_timeout_as_failure(self) -> None:
        """Test circuit breaker records timeout exceptions as failures."""

        def handle_request(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("Request timed out")

        transport = httpx.MockTransport(handle_request)
        connector = TestConnector(transport)
        connector.connect()

        # Trigger timeouts
        for _ in range(3):
            with pytest.raises(TransientOrderError, match="timed out"):
                connector._request("GET", "/test")

        # Circuit should be open
        assert connector.get_circuit_breaker_state() == CircuitBreakerState.OPEN

        connector.disconnect()

    def test_circuit_breaker_records_network_error_as_failure(self) -> None:
        """Test circuit breaker records network errors as failures."""

        def handle_request(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(handle_request)
        connector = TestConnector(transport)
        connector.connect()

        # Trigger network errors
        for _ in range(3):
            with pytest.raises(TransientOrderError, match="failed"):
                connector._request("GET", "/test")

        # Circuit should be open
        assert connector.get_circuit_breaker_state() == CircuitBreakerState.OPEN

        connector.disconnect()

    def test_circuit_breaker_metrics(self) -> None:
        """Test circuit breaker metrics are exposed correctly."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"success": True})
        )
        connector = TestConnector(transport)
        connector.connect()

        metrics = connector.get_circuit_breaker_metrics()

        assert "state" in metrics
        assert "failure_rate" in metrics
        assert "time_until_recovery" in metrics
        assert "last_trip_reason" in metrics
        assert metrics["state"] == "closed"
        assert metrics["failure_rate"] == 0.0

        connector.disconnect()

    def test_circuit_breaker_manual_reset(self) -> None:
        """Test manual circuit breaker reset."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(500, json={"error": "server error"})
        )
        connector = TestConnector(transport)
        connector.connect()

        # Open circuit breaker
        for _ in range(3):
            with pytest.raises(TransientOrderError):
                connector._request("GET", "/test")

        assert connector.get_circuit_breaker_state() == CircuitBreakerState.OPEN

        # Manual reset
        connector.reset_circuit_breaker()
        assert connector.get_circuit_breaker_state() == CircuitBreakerState.CLOSED

        connector.disconnect()

    def test_circuit_breaker_with_429_rate_limit(self) -> None:
        """Test circuit breaker records 429 responses as failures."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(429, json={"error": "rate limited"})
        )
        connector = TestConnector(transport)
        connector.connect()

        # Trigger rate limit errors
        for _ in range(3):
            with pytest.raises(TransientOrderError, match="rate limited"):
                connector._request("GET", "/test")

        # Circuit should be open
        assert connector.get_circuit_breaker_state() == CircuitBreakerState.OPEN

        connector.disconnect()

    def test_successful_requests_do_not_trip_circuit(self) -> None:
        """Test successful requests keep circuit closed."""
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json={"success": True})
        )
        connector = TestConnector(transport)
        connector.connect()

        # Make multiple successful requests
        for _ in range(10):
            connector._request("GET", "/test")

        # Circuit should remain closed
        assert connector.get_circuit_breaker_state() == CircuitBreakerState.CLOSED
        metrics = connector.get_circuit_breaker_metrics()
        assert metrics["failure_rate"] < 0.5

        connector.disconnect()

    def test_mixed_success_failure_below_threshold(self) -> None:
        """Test mixed results below threshold don't open circuit."""
        call_count = 0

        def handle_request(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            # Alternate success and failure
            if call_count % 3 == 0:
                return httpx.Response(500, json={"error": "server error"})
            return httpx.Response(200, json={"success": True})

        transport = httpx.MockTransport(handle_request)
        connector = TestConnector(transport)
        connector.connect()

        # Make requests with mixed results
        for i in range(6):
            if (i + 1) % 3 == 0:
                with pytest.raises(TransientOrderError):
                    connector._request("GET", "/test")
            else:
                connector._request("GET", "/test")

        # Circuit should remain closed (failures not consecutive)
        assert connector.get_circuit_breaker_state() == CircuitBreakerState.CLOSED

        connector.disconnect()
