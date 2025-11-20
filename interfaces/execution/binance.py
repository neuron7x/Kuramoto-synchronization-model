"""Binance execution connector with authenticated REST and user-stream support."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from uuid import uuid4

import httpx

from domain import Order, OrderSide, OrderStatus, OrderType
from execution.connectors import OrderError

from .common import (
    AuthenticatedRESTExecutionConnector,
    CredentialError,
    HMACSigner,
)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_STATUS_MAP = {
    "NEW": OrderStatus.OPEN,
    "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
    "FILLED": OrderStatus.FILLED,
    "CANCELED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
}


class BinanceExecutionConnector(AuthenticatedRESTExecutionConnector):
    """Authenticated connector for Binance spot trading."""

    REST_BASE = "https://api.binance.com"
    REST_SANDBOX = "https://testnet.binance.vision"
    WS_BASE = "wss://stream.binance.com:9443/ws"
    WS_SANDBOX = "wss://testnet.binance.vision/ws"
    RECV_WINDOW = 5000

    def __init__(
        self,
        *,
        sandbox: bool = True,
        enable_stream: bool = True,
        http_client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        ws_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._ws_base = self.WS_SANDBOX if sandbox else self.WS_BASE
        self._stream_requested = enable_stream
        super().__init__(
            "BINANCE",
            sandbox=sandbox,
            base_url=self.REST_BASE,
            sandbox_url=self.REST_SANDBOX,
            ws_url=None,
            credential_provider=None,
            optional_credential_keys=None,
            http_client=http_client,
            transport=transport,
            ws_factory=ws_factory,
            enable_stream=False,
        )
        self._listen_key: str | None = None
        self._order_symbol_map: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self, credentials: Mapping[str, str] | None = None) -> None:
        super().connect(credentials=credentials)
        if self._stream_requested:
            self._initialise_stream()

    # ------------------------------------------------------------------
    # REST signature helpers
    # ------------------------------------------------------------------

    def _create_signer(self, credentials: Mapping[str, str]) -> HMACSigner:
        return HMACSigner(credentials["API_SECRET"], algorithm="sha256")

    def _api_headers(self) -> dict[str, str]:
        return {"X-MBX-APIKEY": self.credentials["API_KEY"]}

    def _apply_signature(
        self,
        method: str,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str],
        body: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, str], dict[str, Any] | None]:
        params = {k: v for k, v in params.items() if v is not None}
        params.setdefault("recvWindow", self.RECV_WINDOW)
        params["timestamp"] = int(time.time() * 1000)
        headers.update(self._api_headers())
        query = urlencode(sorted((key, str(value)) for key, value in params.items()))
        signature = self._signer.sign(query)
        params["signature"] = signature
        # Binance expects query-string payloads
        return params, headers, None

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        if self._signer is None:
            raise CredentialError("Connector must be connected before placing orders")

        if idempotency_key:
            reconciled = self._idempotency_store.reconcile(
                idempotency_key,
                self._reconcile_remote,
            )
            if reconciled is not None:
                return self._to_order(order, reconciled)

        client_id = idempotency_key or self._generate_client_id()
        params = self._build_order_payload(order, client_id)
        try:
            response = self._request(
                "POST",
                "/api/v3/order",
                params=params,
                idempotency_key=client_id,
            )
        except (
            httpx.HTTPStatusError
        ) as exc:  # pragma: no cover - httpx raises with status context
            raise OrderError(str(exc)) from exc
        data = response.json()
        order_id = data.get("orderId")
        if order_id:
            self._order_symbol_map[str(order_id)] = order.symbol
        self._idempotency_store.put(
            client_id,
            {
                "client_order_id": client_id,
                "order_id": str(data.get("orderId")),
                "symbol": order.symbol,
            },
        )
        return self._to_order(order, data)

    def cancel_order(self, order_id: str) -> bool:
        symbol = self._order_symbol_map.get(order_id)
        if not symbol:
            raise OrderError("Unknown symbol for order cancellation")
        params = {"symbol": symbol, "orderId": order_id}
        try:
            self._request("DELETE", "/api/v3/order", params=params)
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return False
            raise OrderError(str(exc)) from exc

    def fetch_order(self, order_id: str) -> Order:
        symbol = self._order_symbol_map.get(order_id)
        if not symbol:
            raise OrderError("Unknown symbol for order lookup")
        params = {"symbol": symbol, "orderId": order_id}
        response = self._request("GET", "/api/v3/order", params=params)
        return self._to_order_from_remote(response.json())

    def open_orders(self) -> list[Order]:
        response = self._request("GET", "/api/v3/openOrders", params={})
        return [self._to_order_from_remote(payload) for payload in response.json()]

    def get_positions(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/api/v3/account", params={})
        balances = response.json().get("balances", [])
        return [
            balance
            for balance in balances
            if float(balance.get("free", 0)) or float(balance.get("locked", 0))
        ]

    # ------------------------------------------------------------------
    # Idempotency helpers
    # ------------------------------------------------------------------

    def _generate_client_id(self) -> str:
        return f"tp-{uuid4().hex[:24]}"

    def _reconcile_remote(self, cached: Mapping[str, str]) -> Mapping[str, Any] | None:
        symbol = cached.get("symbol")
        client_id = cached.get("client_order_id")
        if not symbol or not client_id:
            return None
        try:
            response = self._request(
                "GET",
                "/api/v3/order",
                params={"symbol": symbol, "origClientOrderId": client_id},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise OrderError(str(exc)) from exc
        return response.json()

    # ------------------------------------------------------------------
    # Stream handling
    # ------------------------------------------------------------------

    def _initialise_stream(self) -> None:
        response = self._request(
            "POST",
            "/api/v3/userDataStream",
            signed=False,
            headers=self._api_headers(),
            idempotent=True,
        )
        payload = response.json()
        listen_key = payload.get("listenKey")
        if not listen_key:
            raise OrderError("Failed to negotiate Binance listen key")
        self._listen_key = listen_key
        self._ws_url = f"{self._ws_base}/{listen_key}"
        self._ws_enabled = True
        self._start_streaming()

    def _handle_stream_payload(self, payload: dict[str, Any]) -> None:
        event_type = str(payload.get("e") or "").lower()
        if event_type == "executionreport":
            filled_qty = _safe_float(payload.get("l")) or 0.0
            normalized = {
                "type": "fill",
                "symbol": payload.get("s"),
                "order_id": str(payload.get("i")),
                "client_order_id": payload.get("c"),
                "status": payload.get("X"),
                "filled_qty": filled_qty,
                "fill_price": _safe_float(payload.get("L")) or 0.0,
                "event_time": payload.get("E"),
                "cumulative_qty": _safe_float(payload.get("z")),
                "average_price": _safe_float(payload.get("ap")),
            }
            quote_qty = _safe_float(payload.get("Z"))
            if quote_qty is not None:
                normalized["quote_qty"] = quote_qty
            self._event_queue.put(normalized)
            return
        if event_type == "outboundaccountposition":
            balances: list[dict[str, Any]] = []
            for entry in payload.get("B", []):
                if not isinstance(entry, Mapping):
                    continue
                asset = str(entry.get("a") or entry.get("asset") or "").upper()
                if not asset:
                    continue
                free = _safe_float(entry.get("f") or entry.get("free"))
                locked = _safe_float(entry.get("l") or entry.get("locked"))
                balance_entry: dict[str, Any] = {"asset": asset}
                if free is not None:
                    balance_entry["free"] = free
                if locked is not None:
                    balance_entry["locked"] = locked
                total = _safe_float(entry.get("T") or entry.get("balance"))
                if total is None and free is not None and locked is not None:
                    total = free + locked
                if total is not None:
                    balance_entry["total"] = total
                balances.append(balance_entry)
            if balances:
                self._event_queue.put(
                    {
                        "type": "balance",
                        "balances": balances,
                        "event_time": payload.get("E"),
                    }
                )
            return
        if event_type == "balanceupdate":
            asset = str(payload.get("a") or "").upper()
            delta = _safe_float(payload.get("d"))
            if asset and delta is not None:
                self._event_queue.put(
                    {
                        "type": "balance",
                        "balances": [{"asset": asset, "delta": delta}],
                        "event_time": payload.get("E"),
                    }
                )
            return
        super()._handle_stream_payload(payload)

    # ------------------------------------------------------------------
    # Translation helpers
    # ------------------------------------------------------------------

    def _build_order_payload(self, order: Order, client_id: str) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": order.symbol,
            "side": order.side.name.upper(),
            "type": self._binance_order_type(order.order_type),
            "quantity": self._format_decimal(order.quantity),
            "newClientOrderId": client_id,
        }
        if order.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT}:
            if order.price is None:
                raise OrderError("Limit and stop-limit orders require a price")
            params["price"] = self._format_decimal(order.price)
            params.setdefault("timeInForce", "GTC")
        if order.stop_price is not None:
            params["stopPrice"] = self._format_decimal(order.stop_price)
        return params

    @staticmethod
    def _format_decimal(value: float) -> str:
        return ("{0:.10f}".format(value)).rstrip("0").rstrip(".")

    @staticmethod
    def _binance_order_type(order_type: OrderType) -> str:
        mapping = {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.STOP: "STOP_LOSS",
            OrderType.STOP_LIMIT: "STOP_LOSS_LIMIT",
        }
        return mapping.get(order_type, "MARKET")

    def _to_order(self, template: Order, payload: Mapping[str, Any]) -> Order:
        order = replace(template)
        order_id = payload.get("orderId") or payload.get("i")
        if not order_id:
            raise OrderError("Binance response missing order identifier")
        order.mark_submitted(str(order_id))
        self._order_symbol_map[str(order_id)] = order.symbol
        status = payload.get("status") or payload.get("X")
        if status:
            order.status = _STATUS_MAP.get(status, OrderStatus.PENDING)
        executed = float(payload.get("executedQty", payload.get("z", 0)))
        if executed:
            last_price = float(payload.get("avgPrice", 0) or 0)
            if not last_price and executed:
                cumulative_quote = float(
                    payload.get("cummulativeQuoteQty", payload.get("Z", 0))
                )
                if cumulative_quote:
                    last_price = cumulative_quote / executed
            if last_price:
                order.record_fill(executed, last_price)
            else:
                # Fallback to registering quantity without price impact
                order.filled_quantity = executed
                order.status = OrderStatus.PARTIALLY_FILLED
        return order

    def _to_order_from_remote(self, payload: Mapping[str, Any]) -> Order:
        symbol = payload.get("symbol") or payload.get("s")
        side = payload.get("side") or payload.get("S") or OrderSide.BUY.value
        quantity_raw = payload.get("origQty", payload.get("q"))
        if not symbol or quantity_raw is None:
            raise OrderError("Binance order payload missing symbol or quantity")
        quantity = float(quantity_raw)
        if quantity <= 0:
            raise OrderError("Binance order quantity must be positive")
        price = payload.get("price") or payload.get("p")
        base_order = Order(
            symbol=symbol,
            side=side.lower(),
            quantity=quantity,
            price=float(price) if price else None,
            order_type=OrderType.LIMIT if price else OrderType.MARKET,
        )
        order_id = payload.get("orderId") or payload.get("i")
        if order_id:
            self._order_symbol_map[str(order_id)] = symbol
        return self._to_order(base_order, payload)
