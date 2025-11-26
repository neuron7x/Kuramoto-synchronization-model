from __future__ import annotations

import socket
import time
from typing import Any, Mapping

import pytest

pactman = pytest.importorskip(
    "pactman", reason="pactman is required for contract tests"
)
mock_module = pytest.importorskip(
    "pactman.mock", reason="pactman.mock is required for contract tests"
)

Consumer = pactman.Consumer
Provider = pactman.Provider
mock_server = mock_module.mock_server

from domain import Order, OrderSide, OrderStatus, OrderType  # noqa: E402
from execution.adapters.base import RESTWebSocketConnector  # noqa: E402


def _allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("localhost", 0))
        return sock.getsockname()[1]


def _wait_for_service(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            if time.monotonic() >= deadline:
                raise RuntimeError("Pact mock server did not start in time")
            time.sleep(0.05)


class _PactExecutionConnector(RESTWebSocketConnector):
    """Lightweight connector used solely for consumer contract tests."""

    def __init__(self, *, base_url: str) -> None:
        super().__init__(name="pact-broker", base_url=base_url, sandbox=True)

    def _resolve_credentials(
        self, credentials: Mapping[str, str] | None
    ) -> Mapping[str, str]:
        return dict(credentials or {})

    def _sign_request(  # type: ignore[override]
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any],
        json_payload: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, str], Any | None]:
        return params, json_payload, headers, None

    def _order_endpoint(self) -> str:  # type: ignore[override]
        return "/orders"

    def _build_place_payload(  # type: ignore[override]
        self, order: Order, idempotency_key: str | None
    ) -> dict[str, str]:
        payload = {
            "symbol": order.symbol,
            "side": order.side.value,
            "type": order.order_type.value,
            "quantity": str(order.quantity),
        }
        if order.price is not None:
            payload["price"] = str(order.price)
        if idempotency_key:
            payload["clientOrderId"] = idempotency_key
        return payload

    def _parse_order(  # type: ignore[override]
        self, payload: Mapping[str, Any], *, original: Order | None = None
    ) -> Order:
        order_id = str(payload.get("orderId") or payload.get("id") or "")
        symbol = str(payload.get("symbol") or original.symbol if original else "")
        side_value = str(
            payload.get("side") or (original.side.value if original else "buy")
        )
        type_value = str(
            payload.get("type") or (original.order_type.value if original else "market")
        )
        status_value = str(
            payload.get("status") or (original.status.value if original else "open")
        )
        quantity_raw = payload.get("quantity")
        price_raw = payload.get("price")
        filled_raw = payload.get("filled") or payload.get("filled_quantity") or 0
        average_raw = payload.get("average_price")

        quantity = (
            float(quantity_raw) if quantity_raw is not None else original.quantity
        )
        price = float(price_raw) if price_raw is not None else original.price
        filled = float(filled_raw) if filled_raw is not None else 0.0
        average_price = (
            float(average_raw)
            if average_raw is not None
            else (original.average_price if original else None)
        )

        return Order(
            symbol=symbol,
            side=OrderSide(side_value.lower()),
            quantity=quantity,
            price=price,
            order_type=OrderType(type_value.lower()),
            order_id=order_id or None,
            status=OrderStatus(status_value.lower()),
            filled_quantity=filled,
            average_price=average_price,
        )

    def _cancel_endpoint(self, order_id: str) -> tuple[str, dict[str, Any]]:  # type: ignore[override]
        return f"/orders/{order_id}", {}

    def _fetch_endpoint(self, order_id: str) -> tuple[str, dict[str, Any]]:  # type: ignore[override]
        return f"/orders/{order_id}", {}

    def _open_orders_endpoint(self) -> tuple[str, dict[str, Any]]:  # type: ignore[override]
        return "/orders", {}

    def _positions_endpoint(self) -> tuple[str, dict[str, Any]]:  # type: ignore[override]
        return "/positions", {}

    def _parse_positions(self, payload: Mapping[str, Any] | list[Any]) -> list[dict]:  # type: ignore[override]
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, Mapping)]
        return [dict(payload)] if isinstance(payload, Mapping) else []

    def _handle_stream_message(self, payload: Mapping[str, Any]) -> None:  # type: ignore[override]
        # Streaming is not exercised in the contract tests.
        return None


@pytest.fixture()
def execution_broker_pact(tmp_path_factory: pytest.TempPathFactory):
    port = _allocate_port()
    pact = Consumer("TradePulseExecutionEngine").has_pact_with(
        Provider("SandboxExecutionBroker"),
        host_name="localhost",
        port=port,
        pact_dir=str(tmp_path_factory.mktemp("pacts")),
        use_mocking_server=True,
    )
    try:
        yield pact
    finally:
        if getattr(pact, "_mock_handler", None) is not None:
            pact.stop_service()
        mock_server._providers.pop(pact.provider.name, None)


def test_execution_order_contract(execution_broker_pact) -> None:
    order = Order(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        quantity=1.5,
        price=42000.0,
        order_type=OrderType.LIMIT,
    )
    request_payload = {
        "symbol": order.symbol,
        "side": order.side.value,
        "type": order.order_type.value,
        "quantity": str(order.quantity),
        "price": str(order.price),
        "clientOrderId": "contract-123",
    }
    response_payload = {
        "orderId": "sandbox-0001",
        "symbol": order.symbol,
        "side": order.side.value,
        "type": order.order_type.value,
        "status": OrderStatus.OPEN.value,
        "quantity": str(order.quantity),
        "price": str(order.price),
        "filled": "0",
    }

    (
        execution_broker_pact.given("matching engine accepting limit orders")
        .upon_receiving("a limit order placement")
        .with_request("post", "/orders", query=request_payload)
        .will_respond_with(
            200, body=response_payload, headers={"Content-Type": "application/json"}
        )
    )

    base_url = f"http://127.0.0.1:{execution_broker_pact.port}"
    connector = _PactExecutionConnector(base_url=base_url)
    connector.connect(credentials={})
    try:
        if getattr(execution_broker_pact, "_mock_handler", None) is None:
            execution_broker_pact.start_service()
        with execution_broker_pact:
            _wait_for_service(int(execution_broker_pact.port))
            submitted = connector.place_order(order, idempotency_key="contract-123")
        assert submitted.order_id == response_payload["orderId"]
        assert submitted.status is OrderStatus.OPEN
        assert submitted.quantity == pytest.approx(order.quantity)
        assert submitted.remaining_quantity == pytest.approx(order.quantity)
    finally:
        connector.disconnect()


def test_execution_order_contract_rejects_negative_quantities(
    execution_broker_pact,
) -> None:
    order = Order(
        symbol="ETH-USD",
        side=OrderSide.SELL,
        quantity=2.0,
        price=2800.0,
        order_type=OrderType.LIMIT,
    )
    request_payload = {
        "symbol": order.symbol,
        "side": order.side.value,
        "type": order.order_type.value,
        "quantity": str(order.quantity),
        "price": str(order.price),
    }
    response_payload = {
        "orderId": "sandbox-0002",
        "symbol": order.symbol,
        "side": order.side.value,
        "type": order.order_type.value,
        "status": OrderStatus.OPEN.value,
        "quantity": "-5.0",
        "price": str(order.price),
        "filled": "0",
    }

    (
        execution_broker_pact.given("provider violates quantity invariant")
        .upon_receiving("an order placement with invalid fill")
        .with_request("post", "/orders", query=request_payload)
        .will_respond_with(
            200, body=response_payload, headers={"Content-Type": "application/json"}
        )
    )

    base_url = f"http://127.0.0.1:{execution_broker_pact.port}"
    connector = _PactExecutionConnector(base_url=base_url)
    connector.connect(credentials={})
    try:
        if getattr(execution_broker_pact, "_mock_handler", None) is None:
            execution_broker_pact.start_service()
        with execution_broker_pact:
            _wait_for_service(int(execution_broker_pact.port))
            with pytest.raises(ValueError, match="quantity must be positive"):
                connector.place_order(order)
    finally:
        connector.disconnect()
