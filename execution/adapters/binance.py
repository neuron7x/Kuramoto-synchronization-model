# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Production-grade Binance REST/WebSocket connector."""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from typing import Any, Dict, Iterable, Mapping
from urllib.parse import urlencode

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
    "NEW": OrderStatus.OPEN,
    "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
    "FILLED": OrderStatus.FILLED,
    "CANCELED": OrderStatus.CANCELLED,
    "PENDING_CANCEL": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
    "EXPIRED": OrderStatus.CANCELLED,
}

_TYPE_ALIASES: dict[str, OrderType] = {
    "market": OrderType.MARKET,
    "limit": OrderType.LIMIT,
    "limit_maker": OrderType.LIMIT,
    "stop": OrderType.STOP,
    "stop_loss": OrderType.STOP,
    "stop_market": OrderType.STOP,
    "take_profit": OrderType.STOP,
    "trailing_stop_market": OrderType.STOP,
    "stop_limit": OrderType.STOP_LIMIT,
    "stop_loss_limit": OrderType.STOP_LIMIT,
    "take_profit_limit": OrderType.STOP_LIMIT,
}


class BinanceRESTConnector(RESTWebSocketConnector):
    """Authenticated connector covering core Binance spot order flows."""

    def __init__(
        self,
        *,
        sandbox: bool = True,
        http_client=None,
        ws_factory=None,
    ) -> None:
        base_url = (
            "https://testnet.binance.vision" if sandbox else "https://api.binance.com"
        )
        stream_base = "wss://stream.binance.com:9443/ws"
        if sandbox:
            stream_base = "wss://testnet.binance.vision/ws"
        super().__init__(
            name="binance",
            base_url=base_url,
            sandbox=sandbox,
            http_client=http_client,
            ws_factory=ws_factory,
        )
        self._stream_base = stream_base.rstrip("/")
        # Credentials are loaded separately via authenticate() method, not hardcoded
        self._api_key: str | None = None  # nosec B105 - not a hardcoded password
        self._api_secret: str | None = None  # nosec B105 - not a hardcoded password
        self._listen_key: str | None = None
        self._time_offset = 0.0
        self._last_time_sync = 0.0
        self._time_sync_interval = 60.0
        self._listen_key_stop = threading.Event()
        self._listen_key_thread: threading.Thread | None = None
        self._listen_key_refresh_interval = 30 * 60.0
        self._symbol_info: dict[str, Mapping[str, Any]] = {}
        self._rate_weights: dict[str, int] = {
            "GET /api/v3/time": 1,
            "GET /api/v3/exchangeInfo": 10,
            "POST /api/v3/order": 1,
            "DELETE /api/v3/order": 1,
            "GET /api/v3/order": 2,
            "GET /api/v3/openOrders": 3,
            "GET /api/v3/account": 10,
            "POST /api/v3/userDataStream": 1,
            "PUT /api/v3/userDataStream": 1,
            "POST /api/v3/order/cancelReplace": 1,
        }

    def connect(self, credentials: Mapping[str, str] | None = None) -> None:
        super().connect(credentials)
        try:
            self._synchronize_time(force=True)
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.warning(
                "Failed to synchronize Binance server time", extra={"error": str(exc)}
            )
        try:
            self._refresh_exchange_info()
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.warning(
                "Failed to refresh Binance exchange info", extra={"error": str(exc)}
            )

    # ------------------------------------------------------------------
    # Abstract hook implementations
    def _resolve_credentials(
        self, credentials: Mapping[str, str] | None
    ) -> Mapping[str, str]:
        supplied = {str(k).lower(): str(v) for k, v in (credentials or {}).items()}
        api_key = (
            supplied.get("api_key")
            or os.getenv("BINANCE_API_KEY")
            or os.getenv("BINANCE_KEY")
        )
        api_secret = (
            supplied.get("api_secret")
            or os.getenv("BINANCE_API_SECRET")
            or os.getenv("BINANCE_SECRET")
        )
        recv_window = supplied.get("recv_window") or os.getenv("BINANCE_RECV_WINDOW")
        if not api_key or not api_secret:
            raise ValueError("Binance credentials must provide api_key and api_secret")
        self._api_key = api_key
        self._api_secret = api_secret
        payload: Dict[str, str] = {"api_key": api_key, "api_secret": api_secret}
        if recv_window:
            payload["recv_window"] = str(recv_window)
        return payload

    def _default_headers(self) -> Dict[str, str]:
        headers = super()._default_headers()
        if self._api_key:
            headers["X-MBX-APIKEY"] = self._api_key
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
                "Binance connector signing requested without credentials"
            )
        params = dict(params)
        self._ensure_time_sync()
        params.setdefault("timestamp", str(self._timestamp_ms()))
        recv_window = (
            self._credentials.get("recv_window")
            if hasattr(self, "_credentials")
            else None
        )
        if recv_window and "recvWindow" not in params:
            params["recvWindow"] = str(recv_window)
        query = urlencode(sorted(params.items()))
        signature = hmac.new(
            self._api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params, None, headers, None

    def _order_endpoint(self) -> str:
        return "/api/v3/order"

    def _build_place_payload(
        self, order: Order, idempotency_key: str | None
    ) -> Dict[str, Any]:
        order_type = order.order_type
        binance_type = order_type.value.upper()
        if order_type is OrderType.STOP:
            binance_type = (
                "STOP_LOSS" if order.side is OrderSide.SELL else "TAKE_PROFIT"
            )
        elif order_type is OrderType.STOP_LIMIT:
            binance_type = (
                "STOP_LOSS_LIMIT"
                if order.side is OrderSide.SELL
                else "TAKE_PROFIT_LIMIT"
            )
        payload: Dict[str, Any] = {
            "symbol": order.symbol.upper(),
            "side": order.side.value.upper(),
            "type": binance_type,
            "quantity": f"{order.quantity:.10f}",
        }
        if (
            order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT}
            and order.price is not None
        ):
            payload["price"] = f"{order.price:.10f}"
            payload["timeInForce"] = "GTC"
        if order.stop_price is not None:
            payload["stopPrice"] = f"{order.stop_price:.10f}"
            if order_type is OrderType.STOP and order.price is not None:
                payload["price"] = f"{order.price:.10f}"
        if idempotency_key:
            payload["newClientOrderId"] = idempotency_key
        return payload

    def _parse_order(
        self, payload: Mapping[str, Any], *, original: Order | None = None
    ) -> Order:
        symbol_value = _first_present(payload, "symbol")
        symbol = (str(symbol_value).strip() if symbol_value is not None else "") or (
            original.symbol if original else ""
        )
        if not symbol:
            raise ValueError("Order payload did not include symbol")
        side = (
            str(
                _first_present(payload, "side", "S")
                or (original.side.value if original else "buy")
            )
            .strip()
            .lower()
        )
        order_type = self._coerce_order_type(
            str(
                _first_present(payload, "type", "o")
                or (original.order_type.value if original else "market")
            ),
            original,
        )
        order_id_value = _first_present(payload, "orderId", "i", "order_id")
        order_id = str(order_id_value).strip() if order_id_value is not None else ""
        if not order_id:
            raise ValueError("Order payload missing identifier")
        quantity_value = _first_present(payload, "origQty", "q")
        quantity = _coerce_float(
            quantity_value,
            default=float(original.quantity if original else 0.0),
        )
        if quantity <= 0 and original is not None and original.quantity > 0:
            quantity = float(original.quantity)
        price_value = _first_present(payload, "price", "p")
        price = _coerce_optional_float(price_value)
        if price is None and original is not None:
            price = float(original.price) if original.price is not None else None
        filled = _coerce_float(
            _first_present(payload, "executedQty", "z", "filledQty"), default=0.0
        )
        cumulative_quote_value = _first_present(
            payload, "cummulativeQuoteQty", "Z", "cumulativeQuoteQty"
        )
        cumulative_quote = _coerce_optional_float(cumulative_quote_value)
        avg_price_value = _first_present(payload, "avgPrice", "ap")
        average_price = _coerce_optional_float(avg_price_value)
        if average_price is None and filled > 0 and cumulative_quote is not None:
            try:
                average_price = cumulative_quote / filled
            except ZeroDivisionError:  # pragma: no cover - defensive guard
                average_price = None
        status_value = (
            str(_first_present(payload, "status", "X") or "NEW").strip().upper()
        )
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
        symbol = self._lookup_symbol(order_id)
        return self._order_endpoint(), {"symbol": symbol.upper(), "orderId": order_id}

    def _fetch_endpoint(self, order_id: str) -> tuple[str, Dict[str, Any]]:
        symbol = self._lookup_symbol(order_id)
        return self._order_endpoint(), {"symbol": symbol.upper(), "orderId": order_id}

    def _open_orders_endpoint(self) -> tuple[str, Dict[str, Any]]:
        return "/api/v3/openOrders", {}

    def _positions_endpoint(self) -> tuple[str, Dict[str, Any]]:
        return "/api/v3/account", {}

    def _parse_positions(self, payload: Mapping[str, Any]) -> list[dict]:
        raw_balances = payload.get("balances", [])
        if isinstance(raw_balances, Mapping):
            balances_iter: Iterable[Any] = raw_balances.values()
        elif isinstance(raw_balances, Iterable) and not isinstance(
            raw_balances, (str, bytes)
        ):
            balances_iter = raw_balances
        else:
            balances_iter = []
        positions: list[dict] = []
        for balance in balances_iter:
            if not isinstance(balance, Mapping):
                continue
            asset = str(balance.get("asset", "")).strip().upper()
            free_qty = _coerce_optional_float(balance.get("free")) or 0.0
            locked_qty = _coerce_optional_float(balance.get("locked")) or 0.0
            qty = free_qty + locked_qty
            if qty <= 0 or not asset:
                continue
            positions.append(
                {"symbol": asset, "qty": qty, "side": "long", "price": 0.0}
            )
        return positions

    def _stream_url(self) -> str | None:
        response = self._request(
            "POST", "/api/v3/userDataStream", params={}, signed=False
        )
        listen_key = response.get("listenKey")
        if not isinstance(listen_key, str) or not listen_key:
            raise ValueError("Binance userDataStream did not return listenKey")
        self._listen_key = listen_key
        self._start_listen_key_maintenance()
        return f"{self._stream_base}/{listen_key}"

    def _handle_stream_message(self, payload: Mapping[str, Any]) -> None:
        event = str(payload.get("e") or "").lower()
        if event != "executionreport":
            return
        mapped = {
            "symbol": payload.get("s"),
            "orderId": payload.get("i"),
            "side": payload.get("S"),
            "status": payload.get("X"),
            "executedQty": payload.get("z"),
            "cummulativeQuoteQty": payload.get("Z"),
            "price": payload.get("p") or payload.get("L"),
            "avgPrice": payload.get("ap"),
            "origQty": payload.get("q"),
            "type": payload.get("o"),
        }
        order = self._parse_order(mapped)
        with self._lock:
            if order.order_id:
                self._orders[order.order_id] = order

    # ------------------------------------------------------------------
    # Helpers
    def _lookup_symbol(self, order_id: str) -> str:
        with self._lock:
            order = self._orders.get(order_id)
        if order is None:
            raise ValueError(f"Symbol unknown for order_id={order_id}")
        return order.symbol

    def _coerce_order_type(self, value: str, original: Order | None) -> OrderType:
        raw = value.replace("-", "_").replace(" ", "_").strip().lower()
        mapped = _TYPE_ALIASES.get(raw)
        if mapped is not None:
            return mapped
        try:
            return OrderType(raw)
        except ValueError:
            return original.order_type if original is not None else OrderType.MARKET

    def _timestamp_ms(self) -> int:
        return int((time.time() + self._time_offset) * 1000)

    def _ensure_time_sync(self) -> None:
        now = time.monotonic()
        if now - self._last_time_sync < self._time_sync_interval:
            return
        self._synchronize_time()

    def _synchronize_time(self, *, force: bool = False) -> None:
        if self._http_client is None:
            return
        now = time.monotonic()
        if not force and now - self._last_time_sync < self._time_sync_interval:
            return
        response = self._http_client.get("/api/v3/time")
        response.raise_for_status()
        payload = response.json()
        server_time = float(payload.get("serverTime", 0.0))
        if not server_time:
            raise ValueError("Binance time endpoint returned invalid payload")
        self._time_offset = server_time / 1000.0 - time.time()
        self._last_time_sync = now

    def _refresh_exchange_info(self) -> None:
        if self._http_client is None:
            return
        response = self._http_client.get("/api/v3/exchangeInfo")
        response.raise_for_status()
        payload = response.json()
        symbols = payload.get("symbols") or []
        if not isinstance(symbols, list):
            return
        info: dict[str, Mapping[str, Any]] = {}
        for entry in symbols:
            if not isinstance(entry, Mapping):
                continue
            symbol = str(entry.get("symbol") or "").upper()
            if not symbol:
                continue
            info[symbol] = entry
        self._symbol_info = info

    def cancel_replace_order(
        self,
        order_id: str,
        new_order: Order,
        *,
        idempotency_key: str | None = None,
    ) -> Order:
        payload = self._build_place_payload(new_order, idempotency_key)
        symbol = payload.get("symbol") or self._lookup_symbol(order_id)
        payload["symbol"] = symbol
        payload["cancelOrderId"] = order_id
        payload.setdefault("cancelReplaceMode", "STOP_ON_FAILURE")
        response = self._request(
            "POST",
            "/api/v3/order/cancelReplace",
            params=payload,
            signed=True,
        )
        order_payload = (
            response.get("newOrderResponse") if isinstance(response, Mapping) else None
        )
        if not isinstance(order_payload, Mapping):
            order_payload = response
        parsed = self._parse_order(order_payload, original=new_order)
        with self._lock:
            if parsed.order_id:
                self._orders[parsed.order_id] = parsed
            if idempotency_key:
                self._idempotency_cache[idempotency_key] = parsed
        return parsed

    def _start_listen_key_maintenance(self) -> None:
        if self._listen_key_thread and self._listen_key_thread.is_alive():
            return
        self._listen_key_stop.clear()

        def _maintain() -> None:
            while not self._listen_key_stop.wait(self._listen_key_refresh_interval):
                listen_key = self._listen_key
                if not listen_key or not self._connected or self._http_client is None:
                    continue
                try:
                    response = self._http_client.put(
                        "/api/v3/userDataStream", params={"listenKey": listen_key}
                    )
                    response.raise_for_status()
                except Exception as exc:  # pragma: no cover - defensive logging
                    self._logger.warning(
                        "Failed to refresh Binance listen key",
                        extra={"error": str(exc)},
                    )
                    try:
                        response = self._http_client.post(
                            "/api/v3/userDataStream", params={}
                        )
                        response.raise_for_status()
                        new_key = response.json().get("listenKey")
                        if isinstance(new_key, str) and new_key:
                            self._listen_key = new_key
                            self._restart_stream(new_key)
                    except (
                        Exception
                    ) as inner_exc:  # pragma: no cover - defensive logging
                        self._logger.error(
                            "Failed to reacquire Binance listen key",
                            extra={"error": str(inner_exc)},
                        )

        self._listen_key_thread = threading.Thread(
            target=_maintain,
            name="binance-listen-key",
            daemon=True,
        )
        self._listen_key_thread.start()

    def _restart_stream(self, listen_key: str) -> None:
        url = f"{self._stream_base}/{listen_key}"
        self._ws_stop.set()
        thread = self._ws_thread
        if thread is not None:
            thread.join(timeout=5.0)
        self._ws_stop.clear()
        self._start_stream(url)

    def disconnect(self) -> None:
        self._listen_key_stop.set()
        if self._listen_key_thread is not None:
            self._listen_key_thread.join(timeout=5.0)
            self._listen_key_thread = None
        super().disconnect()


def _self_test() -> AdapterDiagnostic:
    checks = []
    try:
        connector = BinanceRESTConnector(sandbox=True)
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
    return AdapterDiagnostic(adapter_id="binance.spot", checks=tuple(checks))


PLUGIN = AdapterPlugin(
    contract=AdapterContract(
        identifier="binance.spot",
        name="Binance Spot",
        provider="Binance",
        version="1.0.0",
        description="Binance spot trading connector using REST and WebSocket APIs.",
        transports={
            "rest": "https://api.binance.com",
            "websocket": "wss://stream.binance.com:9443/ws",
        },
        supports_sandbox=True,
        required_credentials=("api_key", "api_secret"),
        optional_credentials=("recv_window",),
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
            "sandbox_rest": "https://testnet.binance.vision",
            "sandbox_websocket": "wss://testnet.binance.vision/ws",
        },
    ),
    factory=BinanceRESTConnector,
    implementation=BinanceRESTConnector,
    self_test=_self_test,
    module=__name__,
)


__all__ = ["BinanceRESTConnector", "PLUGIN"]
