"""Coinbase execution connector covering REST and WebSocket flows."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import replace
from typing import Any, Callable, Mapping
from uuid import uuid4

import httpx

from domain import Order, OrderSide, OrderStatus, OrderType
from execution.connectors import OrderError

from .common import (
    AuthenticatedRESTExecutionConnector,
    CredentialError,
    CredentialProvider,
    HMACSigner,
)

_STATUS_MAP = {
    "OPEN": OrderStatus.OPEN,
    "FILLED": OrderStatus.FILLED,
    "PARTIAL": OrderStatus.PARTIALLY_FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
}


class CoinbaseExecutionConnector(AuthenticatedRESTExecutionConnector):
    """Coinbase Advanced Trade execution connector."""

    REST_BASE = "https://api.coinbase.com"
    REST_SANDBOX = "https://api-public.sandbox.exchange.coinbase.com"
    WS_BASE = "wss://advanced-trade-ws.coinbase.com"  # Sandbox shares the same endpoint

    def __init__(
        self,
        *,
        sandbox: bool = True,
        enable_stream: bool = True,
        http_client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        ws_factory: Callable[[str], Any] | None = None,
    ) -> None:
        super().__init__(
            "COINBASE",
            sandbox=sandbox,
            base_url=self.REST_BASE,
            sandbox_url=self.REST_SANDBOX,
            ws_url=self.WS_BASE,
            credential_provider=CredentialProvider(
                "COINBASE", required_keys=("API_KEY", "API_SECRET", "API_PASSPHRASE")
            ),
            optional_credential_keys=None,
            http_client=http_client,
            transport=transport,
            ws_factory=ws_factory,
            enable_stream=enable_stream,
        )
        self._order_symbol_map: dict[str, str] = {}

    # ------------------------------------------------------------------
    # REST signing
    # ------------------------------------------------------------------

    def _create_signer(self, credentials: Mapping[str, str]) -> HMACSigner:
        return HMACSigner(credentials["API_SECRET"], algorithm="sha256")

    def _default_headers(self) -> dict[str, str]:
        return {"Accept": "application/json"}

    def _apply_signature(
        self,
        method: str,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str],
        body: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, str], dict[str, Any] | None]:
        if self._signer is None:
            raise CredentialError("Connector must be connected before signing requests")
        creds = dict(self.credentials)
        timestamp = str(int(time.time()))
        request_path = path if path.startswith("/") else f"/{path.lstrip('/')}"
        if body is None:
            payload = ""
        else:
            payload = json.dumps(body, separators=(",", ":"))
        message = f"{timestamp}{method.upper()}{request_path}{payload}"
        digest = hmac.new(
            creds["API_SECRET"].encode(), message.encode(), hashlib.sha256
        ).digest()
        signature = base64.b64encode(digest).decode()
        headers.update(
            {
                "CB-ACCESS-KEY": creds["API_KEY"],
                "CB-ACCESS-SIGN": signature,
                "CB-ACCESS-TIMESTAMP": timestamp,
                "CB-ACCESS-PASSPHRASE": creds.get("API_PASSPHRASE", ""),
                "Content-Type": "application/json",
            }
        )
        return params, headers, body

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        if self._signer is None:
            raise CredentialError("Connector must be connected before placing orders")
        if idempotency_key:
            reconciled = self._idempotency_store.reconcile(
                idempotency_key, self._reconcile_remote
            )
            if reconciled is not None:
                return self._to_order(order, reconciled)
        client_id = idempotency_key or self._generate_client_id()
        body = self._build_payload(order, client_id)
        try:
            response = self._request(
                "POST",
                "/api/v3/brokerage/orders",
                body=body,
                idempotency_key=client_id,
            )
        except httpx.HTTPStatusError as exc:
            raise OrderError(str(exc)) from exc
        payload = response.json()
        order_id = payload.get("order_id") or payload.get("orderId")
        if order_id:
            self._order_symbol_map[str(order_id)] = order.symbol
        self._idempotency_store.put(
            client_id,
            {
                "client_order_id": client_id,
                "order_id": str(order_id) if order_id else "",
                "symbol": order.symbol,
            },
        )
        return self._to_order(order, payload)

    def cancel_order(self, order_id: str) -> bool:
        body = {"order_ids": [order_id]}
        try:
            self._request(
                "POST",
                "/api/v3/brokerage/orders/batch_cancel",
                body=body,
                idempotent=True,
                idempotency_key=f"cancel-{order_id}",
            )
            return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return False
            raise OrderError(str(exc)) from exc

    def fetch_order(self, order_id: str) -> Order:
        response = self._request(
            "GET", f"/api/v3/brokerage/orders/historical/{order_id}"
        )
        return self._to_order_from_remote(response.json())

    def open_orders(self) -> list[Order]:
        response = self._request("GET", "/api/v3/brokerage/orders/historical/best")
        return [
            self._to_order_from_remote(item)
            for item in response.json().get("orders", [])
        ]

    def get_positions(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/api/v3/brokerage/accounts")
        return response.json().get("accounts", [])

    # ------------------------------------------------------------------
    # Idempotency helpers
    # ------------------------------------------------------------------

    def _generate_client_id(self) -> str:
        return f"tp-{uuid4().hex}"

    def _reconcile_remote(self, cached: Mapping[str, str]) -> Mapping[str, Any] | None:
        order_id = cached.get("order_id")
        if not order_id:
            return None
        try:
            response = self._request(
                "GET", f"/api/v3/brokerage/orders/historical/{order_id}"
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise OrderError(str(exc)) from exc
        return response.json()

    # ------------------------------------------------------------------
    # Stream handling
    # ------------------------------------------------------------------

    def _handle_stream_payload(self, payload: dict[str, Any]) -> None:
        events = payload.get("events") or []
        handled = False
        for event in events:
            event_type = str(event.get("type") or "").lower()
            if event_type == "fill":
                normalized = {
                    "type": "fill",
                    "order_id": event.get("order_id"),
                    "product_id": event.get("product_id"),
                    "filled_qty": float(event.get("filled_size", 0)),
                    "price": float(event.get("price", 0)),
                    "event_time": payload.get("timestamp") or event.get("timestamp"),
                    "status": event.get("status"),
                    "cumulative_qty": event.get("cumulative_filled_size"),
                    "average_price": event.get("average_filled_price"),
                }
                self._event_queue.put(normalized)
                handled = True
            elif event_type in {"snapshot", "balance_update", "account"} or event.get(
                "balances"
            ):
                balances: list[dict[str, Any]] = []
                raw_balances = event.get("balances") or event.get("balance_updates")
                if isinstance(raw_balances, Mapping):
                    balance_iter = raw_balances.values()
                else:
                    balance_iter = raw_balances or []
                for entry in balance_iter:
                    if not isinstance(entry, Mapping):
                        continue
                    currency = str(
                        entry.get("currency")
                        or entry.get("asset")
                        or entry.get("symbol")
                        or ""
                    ).upper()
                    if not currency:
                        continue
                    available = entry.get("available_balance") or entry.get("available")
                    hold = entry.get("hold_balance") or entry.get("hold")
                    balance_entry: dict[str, Any] = {"asset": currency}
                    if isinstance(available, Mapping):
                        available = available.get("value")
                    if isinstance(hold, Mapping):
                        hold = hold.get("value")
                    if available is not None:
                        balance_entry["free"] = float(available)
                    if hold is not None:
                        balance_entry["locked"] = float(hold)
                    total = entry.get("total_balance") or entry.get("balance")
                    if isinstance(total, Mapping):
                        total = total.get("value")
                    if total is not None:
                        balance_entry["total"] = float(total)
                    delta = entry.get("delta") or entry.get("change")
                    if delta is not None:
                        balance_entry["delta"] = float(delta)
                    balances.append(balance_entry)
                if balances:
                    self._event_queue.put(
                        {
                            "type": "balance",
                            "balances": balances,
                            "event_time": payload.get("timestamp")
                            or event.get("timestamp"),
                        }
                    )
                    handled = True
        if handled:
            return
        super()._handle_stream_payload(payload)

    # ------------------------------------------------------------------
    # Translation helpers
    # ------------------------------------------------------------------

    def _build_payload(self, order: Order, client_id: str) -> dict[str, Any]:
        config: dict[str, Any]
        if order.order_type == OrderType.MARKET:
            config = {
                "market_market_ioc": {
                    "base_size": self._format_decimal(order.quantity),
                }
            }
        else:
            if order.price is None:
                raise OrderError("Limit orders require a price")
            config = {
                "limit_limit_gtc": {
                    "base_size": self._format_decimal(order.quantity),
                    "limit_price": self._format_decimal(order.price),
                }
            }
        body = {
            "client_order_id": client_id,
            "product_id": order.symbol,
            "side": order.side.name.lower(),
            "order_configuration": config,
        }
        return body

    @staticmethod
    def _format_decimal(value: float) -> str:
        return ("{0:.10f}".format(value)).rstrip("0").rstrip(".")

    def _to_order(self, template: Order, payload: Mapping[str, Any]) -> Order:
        order = replace(template)
        order_id = payload.get("order_id") or payload.get("orderId")
        if not order_id:
            raise OrderError("Coinbase response missing order identifier")
        order.mark_submitted(str(order_id))
        status = payload.get("status") or payload.get("order_status")
        if status:
            order.status = _STATUS_MAP.get(status.upper(), OrderStatus.PENDING)
        filled = float(
            payload.get("filled_size", 0) or payload.get("filled_size_sum", 0) or 0
        )
        price = payload.get("average_filled_price") or payload.get("avg_price")
        if filled:
            fill_price = float(price) if price else order.price or 0.0
            if fill_price:
                order.record_fill(filled, fill_price)
            else:
                order.filled_quantity = filled
                order.status = OrderStatus.PARTIALLY_FILLED
        self._order_symbol_map[str(order_id)] = order.symbol
        return order

    def _to_order_from_remote(self, payload: Mapping[str, Any]) -> Order:
        product_id = payload.get("product_id") or payload.get("productId")
        if not product_id:
            raise OrderError("Coinbase order payload missing product identifier")
        quantity = (
            payload.get("order_configuration", {})
            .get("limit_limit_gtc", {})
            .get("base_size")
        )
        if quantity is None:
            quantity = payload.get("filled_size") or payload.get("base_size") or 0
        quantity = float(quantity)
        if quantity <= 0:
            raise OrderError("Coinbase order quantity must be positive")
        side = payload.get("side", OrderSide.BUY.value)
        price = payload.get("order_configuration", {}).get("limit_limit_gtc", {}).get(
            "limit_price"
        ) or payload.get("average_filled_price")
        order = Order(
            symbol=product_id,
            side=side.lower(),
            quantity=quantity,
            price=float(price) if price else None,
            order_type=OrderType.LIMIT if price else OrderType.MARKET,
        )
        order_id = payload.get("order_id") or payload.get("orderId")
        if order_id:
            self._order_symbol_map[str(order_id)] = order.symbol
        return self._to_order(order, payload)
