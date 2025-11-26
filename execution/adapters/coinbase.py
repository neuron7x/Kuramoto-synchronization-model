# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Production-grade Coinbase Advanced Trade REST/WebSocket connector."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Iterable, Mapping

from domain import Order, OrderSide, OrderStatus, OrderType

from .base import (
    RESTWebSocketConnector,
    _coerce_float,
    _coerce_optional_float,
    _first_present,
)
from .plugin import (
    AdapterCheckResult,
    AdapterContract,
    AdapterDiagnostic,
    AdapterPlugin,
)

_STATUS_MAP = {
    "OPEN": OrderStatus.OPEN,
    "PENDING": OrderStatus.OPEN,
    "FILLED": OrderStatus.FILLED,
    "CANCELED": OrderStatus.CANCELLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "EXPIRED": OrderStatus.CANCELLED,
    "FAILED": OrderStatus.REJECTED,
    "REJECTED": OrderStatus.REJECTED,
    "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
}

_TYPE_ALIASES: dict[str, OrderType] = {
    "market": OrderType.MARKET,
    "market_market_ioc": OrderType.MARKET,
    "limit": OrderType.LIMIT,
    "limit_limit_gtc": OrderType.LIMIT,
    "limit_limit_gtc_post_only": OrderType.LIMIT,
    "stop": OrderType.STOP,
    "stop_limit": OrderType.STOP_LIMIT,
    "stop_limit_stop_limit_gtc": OrderType.STOP_LIMIT,
}


class CoinbaseRESTConnector(RESTWebSocketConnector):
    """Authenticated connector for Coinbase Advanced Trade API."""

    def __init__(
        self,
        *,
        sandbox: bool = True,
        http_client=None,
        ws_factory=None,
    ) -> None:
        base_url = (
            "https://api-public.sandbox.exchange.coinbase.com"
            if sandbox
            else "https://api.coinbase.com"
        )
        if not sandbox:
            base_url = "https://api.coinbase.com"
        api_base = f"{base_url.rstrip('/')}/api/v3/brokerage"
        super().__init__(
            name="coinbase",
            base_url=api_base,
            sandbox=sandbox,
            http_client=http_client,
            ws_factory=ws_factory,
            rate_limit=(120, 1.0),
        )
        self._stream_base = "wss://advanced-trade-ws.coinbase.com"
        if sandbox:
            self._stream_base = (
                "wss://advanced-trade-ws-public.sandbox.exchange.coinbase.com"
            )
        # Credentials are loaded separately via authenticate() method, not hardcoded
        self._api_key: str | None = None  # nosec B105 - not a hardcoded password
        self._api_secret: str | None = None  # nosec B105 - not a hardcoded password
        self._passphrase: str | None = None  # nosec B105 - not a hardcoded password
        self._time_offset = 0.0
        self._last_time_sync = 0.0
        self._time_sync_interval = 120.0
        self._rate_weights: dict[str, int] = {
            "POST /orders": 1,
            "GET /orders": 1,
            "GET /orders/open": 1,
            "GET /accounts": 1,
            "DELETE /orders": 1,
            "POST /orders/cancel": 1,
            "POST /orders/edit": 1,
        }

    def connect(self, credentials: Mapping[str, str] | None = None) -> None:
        super().connect(credentials)
        try:
            self._synchronize_time(force=True)
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.warning(
                "Failed to synchronize Coinbase server time", extra={"error": str(exc)}
            )

    # ------------------------------------------------------------------
    def _resolve_credentials(
        self, credentials: Mapping[str, str] | None
    ) -> Mapping[str, str]:
        supplied = {str(k).lower(): str(v) for k, v in (credentials or {}).items()}
        api_key = supplied.get("api_key") or os.getenv("COINBASE_API_KEY")
        api_secret = supplied.get("api_secret") or os.getenv("COINBASE_API_SECRET")
        passphrase = supplied.get("passphrase") or os.getenv("COINBASE_API_PASSPHRASE")
        if not api_key or not api_secret or not passphrase:
            raise ValueError(
                "Coinbase credentials must provide api_key, api_secret, and passphrase"
            )
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        return {"api_key": api_key, "api_secret": api_secret, "passphrase": passphrase}

    def _default_headers(self) -> Dict[str, str]:
        headers = super()._default_headers()
        if self._api_key:
            headers["CB-ACCESS-KEY"] = self._api_key
        if self._passphrase:
            headers["CB-ACCESS-PASSPHRASE"] = self._passphrase
        headers.setdefault("Content-Type", "application/json")
        return headers

    def _weight_for(self, method: str, path: str) -> int:
        key = f"{method.upper()} {path}"
        return self._rate_weights.get(key, 1)

    def _sign_request(
        self,
        method: str,
        path: str,
        *,
        params: Dict[str, Any],
        json_payload: Dict[str, Any] | None,
        headers: Dict[str, str],
    ) -> tuple[Dict[str, Any], Dict[str, Any] | None, Dict[str, str], Any | None]:
        if self._api_secret is None:
            raise RuntimeError(
                "Coinbase connector signing requested without credentials"
            )
        self._ensure_time_sync()
        timestamp = str(self._timestamp())
        body = json.dumps(json_payload or {}) if json_payload is not None else ""
        request_path = path if path.startswith("/") else f"/{path}"
        message = f"{timestamp}{method.upper()}{request_path}{body}"
        secret = base64.b64decode(self._api_secret)
        signature = hmac.new(secret, message.encode("utf-8"), hashlib.sha256).digest()
        headers["CB-ACCESS-TIMESTAMP"] = timestamp
        headers["CB-ACCESS-SIGN"] = base64.b64encode(signature).decode("utf-8")
        return params, json_payload, headers, None

    def _order_endpoint(self) -> str:
        return "/orders"

    def _build_place_payload(
        self, order: Order, idempotency_key: str | None
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "client_order_id": idempotency_key or order.order_id or "",
            "product_id": order.symbol.replace("_", "-"),
            "side": order.side.value.upper(),
            "order_configuration": {
                "market_market_ioc": None,
            },
        }
        size = f"{order.quantity:.10f}"
        if order.order_type is OrderType.MARKET:
            payload["order_configuration"] = {
                "market_market_ioc": {
                    "base_size": size,
                }
            }
        elif order.order_type is OrderType.LIMIT:
            if order.price is None:
                raise ValueError("Limit orders require price")
            payload["order_configuration"] = {
                "limit_limit_gtc": {
                    "base_size": size,
                    "limit_price": f"{order.price:.10f}",
                }
            }
        elif order.order_type in {OrderType.STOP, OrderType.STOP_LIMIT}:
            if order.stop_price is None:
                raise ValueError("Stop orders require stop_price")
            limit_price = order.price if order.price is not None else order.stop_price
            payload["order_configuration"] = {
                "stop_limit_stop_limit_gtc": {
                    "base_size": size,
                    "limit_price": f"{limit_price:.10f}",
                    "stop_price": f"{order.stop_price:.10f}",
                }
            }
        else:  # pragma: no cover - defensive guard
            raise ValueError(f"Unsupported order type: {order.order_type}")
        return payload

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        if idempotency_key and idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]
        payload = self._build_place_payload(order, idempotency_key)
        response = self._request(
            "POST", self._order_endpoint(), json_payload=payload, signed=True
        )
        submitted = self._parse_order(response, original=order)
        with self._lock:
            self._orders[submitted.order_id or ""] = submitted
            if idempotency_key:
                self._idempotency_cache[idempotency_key] = submitted
        return submitted

    def _parse_order(
        self, payload: Mapping[str, Any], *, original: Order | None = None
    ) -> Order:
        if "order" in payload and isinstance(payload["order"], Mapping):
            payload = payload["order"]
        symbol_value = _first_present(payload, "product_id")
        symbol = (str(symbol_value).strip() if symbol_value is not None else "") or (
            original.symbol if original else ""
        )
        if not symbol:
            raise ValueError("Order payload missing product identifier")
        side = (
            str(
                _first_present(payload, "side")
                or (original.side.value if original else "buy")
            )
            .strip()
            .lower()
        )
        order_type = self._coerce_order_type(
            str(
                _first_present(payload, "order_type", "type")
                or (original.order_type.value if original else "market")
            ),
            original,
        )
        order_id_value = _first_present(payload, "order_id", "id", "orderId")
        order_id = str(order_id_value).strip() if order_id_value is not None else ""
        if not order_id:
            raise ValueError("Order payload missing identifier")
        size_value = _first_present(payload, "size", "base_size", "filled_size")
        quantity = _coerce_float(
            size_value,
            default=float(original.quantity if original else 0.0),
        )
        if quantity <= 0 and original is not None and original.quantity > 0:
            quantity = float(original.quantity)
        filled = _coerce_float(
            _first_present(payload, "filled_size", "executed_value"), default=0.0
        )
        price_value = _first_present(payload, "price", "limit_price")
        price = _coerce_optional_float(price_value)
        if price is None and original is not None:
            price = float(original.price) if original.price is not None else None
        avg_price_val = _first_present(payload, "average_filled_price", "average_price")
        average_price = _coerce_optional_float(avg_price_val)
        status_value = str(_first_present(payload, "status") or "OPEN").strip().upper()
        status = _STATUS_MAP.get(status_value, OrderStatus.OPEN)
        return Order(
            symbol=symbol,
            side=OrderSide(side),
            quantity=(
                quantity if quantity > 0 else (original.quantity if original else 0.0)
            ),
            price=price,
            order_type=order_type,
            order_id=order_id,
            status=status,
            filled_quantity=filled,
            average_price=average_price,
        )

    def _cancel_endpoint(self, order_id: str) -> tuple[str, Dict[str, Any]]:
        return f"/orders/{order_id}", {}

    def _fetch_endpoint(self, order_id: str) -> tuple[str, Dict[str, Any]]:
        return f"/orders/{order_id}", {}

    def _open_orders_endpoint(self) -> tuple[str, Dict[str, Any]]:
        return "/orders/open", {}

    def _positions_endpoint(self) -> tuple[str, Dict[str, Any]]:
        return "/accounts", {}

    def _parse_positions(self, payload: Mapping[str, Any]) -> list[dict]:
        raw_accounts = payload.get("accounts", [])
        if isinstance(raw_accounts, Mapping):
            accounts_iter: Iterable[Any] = raw_accounts.values()
        elif isinstance(raw_accounts, Iterable) and not isinstance(
            raw_accounts, (str, bytes)
        ):
            accounts_iter = raw_accounts
        else:
            accounts_iter = []
        positions: list[dict] = []
        for account in accounts_iter:
            if not isinstance(account, Mapping):
                continue
            balance = account.get("available_balance") or {}
            if not isinstance(balance, Mapping):
                continue
            qty = _coerce_optional_float(balance.get("value")) or 0.0
            if qty <= 0:
                continue
            asset = str(account.get("currency", "")).strip().upper()
            if not asset:
                continue
            positions.append(
                {"symbol": asset, "qty": qty, "side": "long", "price": 0.0}
            )
        return positions

    def _stream_url(self) -> str | None:
        return self._stream_base

    def _handle_stream_message(self, payload: Mapping[str, Any]) -> None:
        message_type = str(payload.get("type") or "").lower()
        if message_type not in {"order_update", "orders"}:
            return
        order_payload = payload.get("order")
        if not isinstance(order_payload, Mapping):
            order_payload = payload
        order = self._parse_order(order_payload)
        with self._lock:
            if order.order_id:
                self._orders[order.order_id] = order

    def _coerce_order_type(self, value: str, original: Order | None) -> OrderType:
        raw = value.replace("-", "_").replace(" ", "_").strip().lower()
        mapped = _TYPE_ALIASES.get(raw)
        if mapped is not None:
            return mapped
        try:
            return OrderType(raw)
        except ValueError:
            return original.order_type if original is not None else OrderType.MARKET

    def _timestamp(self) -> int:
        return int(time.time() + self._time_offset)

    def _ensure_time_sync(self) -> None:
        now = time.monotonic()
        if now - self._last_time_sync < self._time_sync_interval:
            return
        self._synchronize_time()

    def _synchronize_time(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_time_sync < self._time_sync_interval:
            return
        url = "https://api.coinbase.com/v2/time"
        response = self._http_client.get(url) if self._http_client is not None else None
        if response is None:
            return
        response.raise_for_status()
        payload = response.json()
        epoch = payload.get("epoch") or (
            payload.get("data", {}).get("epoch")
            if isinstance(payload.get("data"), Mapping)
            else None
        )
        if epoch is None:
            raise ValueError("Coinbase time endpoint returned invalid payload")
        self._time_offset = float(epoch) - time.time()
        self._last_time_sync = now

    def cancel_replace_order(
        self,
        order_id: str,
        new_order: Order,
        *,
        idempotency_key: str | None = None,
    ) -> Order:
        payload = self._build_place_payload(new_order, idempotency_key)
        client_order_id = payload.get("client_order_id") or idempotency_key or order_id
        request_body = {
            "order_id": order_id,
            "client_order_id": client_order_id,
            "product_id": payload["product_id"],
            "side": payload["side"],
            "order_configuration": payload["order_configuration"],
        }
        response = self._request(
            "POST",
            "/orders/edit",
            json_payload=request_body,
            signed=True,
        )
        order_payload = response.get("order") if isinstance(response, Mapping) else None
        if not isinstance(order_payload, Mapping):
            order_payload = response
        parsed = self._parse_order(order_payload, original=new_order)
        with self._lock:
            if parsed.order_id:
                self._orders[parsed.order_id] = parsed
            if idempotency_key:
                self._idempotency_cache[idempotency_key] = parsed
        return parsed


def _self_test() -> AdapterDiagnostic:
    checks = []
    try:
        connector = CoinbaseRESTConnector(sandbox=True)
        checks.append(
            AdapterCheckResult(
                name="instantiate",
                status="passed",
                detail="Connector instantiated with sandbox configuration",
            )
        )
        if not connector.sandbox:
            raise AssertionError("Connector sandbox flag not set")
        checks.append(
            AdapterCheckResult(
                name="sandbox-flag",
                status="passed",
                detail="Sandbox mode enabled by default",
            )
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        checks.append(
            AdapterCheckResult(name="instantiate", status="failed", detail=str(exc))
        )
    return AdapterDiagnostic(adapter_id="coinbase.advanced-trade", checks=tuple(checks))


PLUGIN = AdapterPlugin(
    contract=AdapterContract(
        identifier="coinbase.advanced-trade",
        name="Coinbase Advanced Trade",
        provider="Coinbase",
        version="1.0.0",
        description="Coinbase Advanced Trade connector using REST and WebSocket APIs.",
        transports={
            "rest": "https://api.coinbase.com",
            "websocket": "wss://advanced-trade-ws.coinbase.com",
        },
        supports_sandbox=True,
        required_credentials=("api_key", "api_secret", "passphrase"),
        capabilities={
            "order_types": [
                "market",
                "limit",
                "stop",
                "stop_limit",
            ],
            "supports_streaming": True,
            "supports_positions": True,
        },
        metadata={
            "sandbox_rest": "https://api-public.sandbox.exchange.coinbase.com/api/v3/brokerage",
            "sandbox_websocket": "wss://advanced-trade-ws-public.sandbox.exchange.coinbase.com",
        },
    ),
    factory=CoinbaseRESTConnector,
    implementation=CoinbaseRESTConnector,
    self_test=_self_test,
    module=__name__,
)


__all__ = ["CoinbaseRESTConnector", "PLUGIN"]
