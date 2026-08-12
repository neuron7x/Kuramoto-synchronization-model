# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Polygon.io ingestion adapter with resilient HTTP and WebSocket support."""

from __future__ import annotations

import json
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

__all__ = ["PolygonIngestionAdapter"]


class PolygonIngestionAdapter(IngestionAdapter):
    """Interact with the Polygon REST and WebSocket APIs."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.polygon.io",
        websocket_url: str = "wss://socket.polygon.io",
        retry: Optional[RetryConfig] = None,
        rate_limit: Optional[RateLimitConfig] = None,
        timeout: Optional[TimeoutConfig] = TimeoutConfig(total_seconds=10.0),
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(retry=retry, rate_limit=rate_limit, timeout=timeout)
        headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.AsyncClient(base_url=base_url, headers=headers)
        self._api_key = api_key
        self._ws_url = websocket_url

    async def fetch(
        self,
        *,
        symbol: str,
        start: str,
        end: str,
        multiplier: int = 1,
        timespan: str = "minute",
        limit: int = 5000,
        adjusted: bool = True,
        instrument_type: InstrumentType = InstrumentType.SPOT,
    ) -> list[Ticker]:
        """Fetch aggregated bars and map them into tick level representation."""

        endpoint = (
            f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start}/{end}"
        )

        async def _call() -> httpx.Response:
            return await self._client.get(
                endpoint,
                params={
                    "adjusted": str(adjusted).lower(),
                    "limit": limit,
                    "sort": "asc",
                },
            )

        response = await self._run_with_policy(_call)
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        ticks: list[Ticker] = []
        for entry in results:
            ts = entry.get("t")
            if isinstance(ts, str) and ts.isdigit():
                ts = int(ts)
            close = entry.get("c")
            volume = entry.get("v", 0)
            if isinstance(ts, (int, float)) and ts > 1e12:
                ts = ts / 1000
            tick = Ticker.create(
                symbol=symbol,
                venue="POLYGON",
                price=close,
                volume=volume,
                instrument_type=instrument_type,
                timestamp=normalize_timestamp(ts),
            )
            ticks.append(tick)
        logger.debug("polygon_fetch", symbol=symbol, count=len(ticks))
        return ticks

    async def stream(
        self,
        *,
        channels: Iterable[str],
        instrument_type: InstrumentType = InstrumentType.SPOT,
    ) -> AsyncIterator[Ticker]:
        """Stream trades/quotes from Polygon's WebSocket."""

        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - defensive
            raise RuntimeError("websockets is required for Polygon streaming") from exc

        channel_param = ",".join(channels)
        attempt = 0
        url = f"{self._ws_url}/stocks"

        while True:
            try:
                async with websockets.connect(
                    url, ping_interval=20, ping_timeout=20
                ) as ws:
                    attempt = 0
                    await ws.send(
                        json.dumps({"action": "auth", "params": self._api_key})
                    )
                    await ws.send(
                        json.dumps({"action": "subscribe", "params": channel_param})
                    )

                    while True:
                        payload = await self._run_with_policy(ws.recv)
                        message = json.loads(payload)
                        if isinstance(message, dict):
                            entries = [message]
                        else:
                            entries = message
                        for entry in entries:
                            if entry.get("ev") not in {"T", "Q"}:
                                continue
                            price = entry.get("p") or entry.get("a")
                            volume = entry.get("s", 0)
                            symbol = entry.get("sym")
                            ts = entry.get("t")
                            if isinstance(ts, str) and ts.isdigit():
                                ts = int(ts)
                            if isinstance(ts, (int, float)) and ts > 1e12:
                                ts = ts / 1000
                            tick = Ticker.create(
                                symbol=symbol,
                                venue="POLYGON",
                                price=price,
                                volume=volume,
                                instrument_type=instrument_type,
                                timestamp=normalize_timestamp(ts),
                            )
                            yield tick
            except Exception as exc:
                attempt += 1
                logger.warning("polygon_ws_reconnect", attempt=attempt, error=str(exc))
                await self._sleep_backoff(attempt)

    async def aclose(self) -> None:
        await self._client.aclose()
