# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import base64
import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

import requests

DEFAULT_TIMEOUT = 15


class HttpClient:
    def __init__(self, base, headers=None, params=None):
        self.base = base.rstrip("/")
        self.headers = headers or {}
        self.params = params or {}

    def get(self, path, params=None, headers=None):
        p = {}
        p.update(self.params)
        if params:
            p.update(params)
        h = {}
        h.update(self.headers)
        if headers:
            h.update(headers)
        r = requests.get(self.base + path, params=p, headers=h, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def post(self, path, data=None, params=None, headers=None):
        p = {}
        p.update(self.params)
        if params:
            p.update(params)
        h = {}
        h.update(self.headers)
        if headers:
            h.update(headers)
        r = requests.post(
            self.base + path, data=data, params=p, headers=h, timeout=DEFAULT_TIMEOUT
        )
        r.raise_for_status()
        return r.json()


def _binance_http():
    return HttpClient("https://api.binance.com")


def _coinbase_http():
    return HttpClient("https://api.coinbase.com/api/v3")


def _kraken_http():
    return HttpClient("https://api.kraken.com/0")


def load_adapter_or_http_client(exchange: str):
    """Load an HTTP client for the exchange.

    For canary tests, we use simple HTTP clients rather than full adapters
    to avoid credential and instantiation complexity.
    """
    if exchange == "binance":
        return _binance_http()
    if exchange == "coinbase":
        return _coinbase_http()
    if exchange == "kraken":
        return _kraken_http()
    raise ValueError(f"Unsupported exchange {exchange}")


def get_server_time(subject) -> int:
    for name in ("get_server_time", "server_time_ms", "time", "now_ms"):
        f = getattr(subject, name, None)
        if callable(f):
            v = f()
            return int(v)
    if isinstance(subject, HttpClient):
        if subject.base == "https://api.binance.com":
            j = subject.get("/api/v3/time")
            return int(j["serverTime"])
        if subject.base == "https://api.coinbase.com/api/v3":
            j = subject.get("/brokerage/time")
            return int(j["epoch_seconds"]) * 1000
        if subject.base == "https://api.kraken.com/0":
            j = subject.get("/public/Time")
            return int(float(j["result"]["unixtime"])) * 1000
    raise RuntimeError("Cannot obtain server time")


def get_exchange_info_or_symbols(subject):
    for name in ("get_exchange_info", "exchange_info", "symbols", "list_symbols"):
        f = getattr(subject, name, None)
        if callable(f):
            v = f()
            if isinstance(v, dict) and "symbols" in v:
                return v
            if isinstance(v, list):
                return {"symbols": v}
    if isinstance(subject, HttpClient):
        if subject.base == "https://api.binance.com":
            j = subject.get("/api/v3/exchangeInfo")
            symbols = [
                s["symbol"]
                for s in j.get("symbols", [])
                if s.get("status") == "TRADING"
            ]
            return {"raw": j, "symbols": symbols}
        if subject.base == "https://api.coinbase.com/api/v3":
            j = subject.get("/brokerage/products", params={"limit": 250})
            products = j.get("products", [])
            symbols = [p["product_id"] for p in products if p.get("status") == "online"]
            return {"raw": j, "symbols": symbols}
        if subject.base == "https://api.kraken.com/0":
            j = subject.get("/public/AssetPairs")
            pairs = j.get("result", {})
            symbols = list(pairs.keys())
            return {"raw": j, "symbols": symbols}
    raise RuntimeError("Cannot obtain exchange info/symbols")


def get_authenticated_balance(subject):
    for name in ("get_balance", "balances", "account_balances", "spot_balance"):
        f = getattr(subject, name, None)
        if callable(f):
            return f()
    if isinstance(subject, HttpClient):
        if subject.base == "https://api.binance.com":
            key = os.getenv("BINANCE_API_KEY")
            secret = os.getenv("BINANCE_API_SECRET")
            if not key or not secret:
                raise RuntimeError("BINANCE_API_KEY/SECRET not set")
            ts = int(time.time() * 1000)
            query = f"timestamp={ts}&recvWindow=5000"
            sig = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            headers = {"X-MBX-APIKEY": key}
            data = subject.get(
                "/api/v3/account",
                params={"timestamp": ts, "recvWindow": 5000, "signature": sig},
                headers=headers,
            )
            # Remove commission fields to keep response focused on balances
            data.pop("makerCommission", None)
            data.pop("takerCommission", None)
            return {"balances": data.get("balances", [])}

        if subject.base == "https://api.coinbase.com/api/v3":
            key = os.getenv("COINBASE_API_KEY")
            secret = os.getenv("COINBASE_API_SECRET")
            passphrase = os.getenv("COINBASE_API_PASSPHRASE", "")
            if not key or not secret:
                raise RuntimeError("COINBASE_API_KEY/SECRET not set")
            ts = str(int(time.time()))
            method = "GET"
            path = "/api/v3/brokerage/accounts"
            prehash = ts + method + path
            sig = base64.b64encode(
                hmac.new(
                    base64.b64decode(secret), prehash.encode(), hashlib.sha256
                ).digest()
            ).decode()
            headers = {
                "CB-ACCESS-KEY": key,
                "CB-ACCESS-SIGN": sig,
                "CB-ACCESS-TIMESTAMP": ts,
                "CB-ACCESS-PASSPHRASE": passphrase,
            }
            # Use a separate client with the base URL (subject.base points to api.coinbase.com/api/v3)
            auth_client = HttpClient("https://api.coinbase.com")
            data = auth_client.get(path, headers=headers)
            accounts = data.get("accounts", [])
            return {
                "accounts": [
                    {
                        "uuid": a.get("uuid"),
                        "currency": a.get("currency"),
                        "available_balance": a.get("available_balance"),
                    }
                    for a in accounts
                ]
            }

        if subject.base == "https://api.kraken.com/0":
            key = os.getenv("KRAKEN_API_KEY")
            secret = os.getenv("KRAKEN_API_SECRET")
            if not key or not secret:
                raise RuntimeError("KRAKEN_API_KEY/SECRET not set")
            nonce = str(int(time.time() * 1000))
            path = "/0/private/Balance"
            postdata = {"nonce": nonce}
            postdata_str = urlencode(postdata)
            sha256 = hashlib.sha256((nonce + postdata_str).encode()).digest()
            message = path.encode() + sha256
            sig = base64.b64encode(
                hmac.new(base64.b64decode(secret), message, hashlib.sha512).digest()
            ).decode()
            headers = {
                "API-Key": key,
                "API-Sign": sig,
                "Content-Type": "application/x-www-form-urlencoded",
            }
            # Use a separate client with the base URL (subject.base points to api.kraken.com/0)
            auth_client = HttpClient("https://api.kraken.com")
            data = auth_client.post(path, data=postdata, headers=headers)
            if data.get("error"):
                raise RuntimeError(f"Kraken error: {data['error']}")
            return {"balances": data.get("result", {})}

    raise RuntimeError("Cannot obtain authenticated balance")
