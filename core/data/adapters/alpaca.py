# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Alpaca Markets ingestion adapter with resilient HTTP/WebSocket support."""

from __future__ import annotations

import json
from datetime import datetime
from typing import AsyncIterator, Iterable, Optional

import httpx

from core.data.adapters.base import (
    IngestionAdapter,
    RateLimitConfig,
    RetryConfig,
    TimeoutConfig,
)
from core.data.models import InstrumentType
from core.data.models import PriceTick as Ticker
from core.data.timeutils import normalize_timestamp
from core.utils.logging import get_logger

logger = get_logger(__name__)

__all__ = ["AlpacaIngestionAdapter"]


def _parse_timestamp(value: object) -> datetime | float | int:
    if isinstance(value, str):
        normalised = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(normalised)
    return value  # type: ignore[return-value]


class AlpacaIngestionAdapter(IngestionAdapter):
    """Interact with the Alpaca data APIs for historical + streaming ticks."""

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        base_url: str = "https://data.alpaca.markets",
        stream_url: str = "wss://stream.data.alpaca.markets/v2/iex",
        retry: Optional[RetryConfig] = None,
        rate_limit: Optional[RateLimitConfig] = None,
        timeout: Optional[TimeoutConfig] = TimeoutConfig(total_seconds=10.0),
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(retry=retry, rate_limit=rate_limit, timeout=timeout)
        headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
        }
        self._client = client or httpx.AsyncClient(base_url=base_url, headers=headers)
        self._api_key = api_key
        self._api_secret = api_secret
        self._stream_url = stream_url

    async def fetch(
        self,
        *,
        symbol: str,
        start: str,
        end: str,
        limit: int = 1000,
        instrument_type: InstrumentType = InstrumentType.SPOT,
    ) -> list[Ticker]:
        """Fetch trades from Alpaca's REST API."""

        endpoint = f"/v2/stocks/{symbol}/trades"

        async def _call() -> httpx.Response:
            return await self._client.get(
                endpoint,
                params={
                    "start": start,
                    "end": end,
                    "limit": limit,
                    "sort": "asc",
                },
            )

        response = await self._run_with_policy(_call)
        response.raise_for_status()
        payload = response.json()
        trades = payload.get("trades", [])
        ticks: list[Ticker] = []
        for trade in trades:
            ts_value = _parse_timestamp(trade.get("t") or trade.get("timestamp"))
            price = trade.get("p") or trade.get("price")
            volume = trade.get("s") or trade.get("size", 0)
            tick = Ticker.create(
                symbol=symbol,
                venue="ALPACA",
                price=price,
                volume=volume,
                instrument_type=instrument_type,
                timestamp=normalize_timestamp(ts_value),
            )
            ticks.append(tick)
        logger.debug("alpaca_fetch", symbol=symbol, count=len(ticks))
        return ticks

    async def stream(
        self,
        *,
        channels: Iterable[str],
        instrument_type: InstrumentType = InstrumentType.SPOT,
    ) -> AsyncIterator[Ticker]:
        """Stream live trades from Alpaca's websocket."""

        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - defensive
            raise RuntimeError("websockets is required for Alpaca streaming") from exc

        attempt = 0
        auth_payload = json.dumps(
            {
                "action": "auth",
                "key": self._api_key,
                "secret": self._api_secret,
            }
        )
        subscribe_payload = json.dumps(
            {"action": "subscribe", "trades": list(channels)}
        )

        while True:
            try:
                async with websockets.connect(
                    self._stream_url, ping_interval=20, ping_timeout=20
                ) as ws:
                    attempt = 0
                    await ws.send(auth_payload)
                    await ws.send(subscribe_payload)

                    while True:
                        payload = await self._run_with_policy(ws.recv)
                        message = json.loads(payload)
                        for entry in message:
                            if entry.get("T") != "t":
                                continue
                            symbol = entry.get("S")
                            price = entry.get("p")
                            volume = entry.get("s", 0)
                            ts = _parse_timestamp(entry.get("t"))
                            tick = Ticker.create(
                                symbol=symbol,
                                venue="ALPACA",
                                price=price,
                                volume=volume,
                                instrument_type=instrument_type,
                                timestamp=normalize_timestamp(ts),
                            )
                            yield tick
            except Exception as exc:
                attempt += 1
                logger.warning("alpaca_ws_reconnect", attempt=attempt, error=str(exc))
                await self._sleep_backoff(attempt)

    async def aclose(self) -> None:
        await self._client.aclose()
