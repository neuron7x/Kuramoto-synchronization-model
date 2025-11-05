"""CCXT-powered ingestion adapter supporting REST and WebSocket sources."""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator, Callable, Optional

from core.data.adapters.base import IngestionAdapter, RateLimitConfig, RetryConfig
from core.data.models import InstrumentType
from core.data.models import PriceTick as Ticker
from core.data.timeutils import normalize_timestamp
from core.utils.logging import get_logger

logger = get_logger(__name__)

__all__ = ["CCXTIngestionAdapter"]


def _load_exchange_factory(exchange_id: str) -> Callable[[dict[str, Any]], Any]:
    try:
        import ccxt.async_support as ccxt_async
    except ImportError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(
            "ccxt must be installed to use the CCXTIngestionAdapter"
        ) from exc

    exchange_id = exchange_id.lower()
    if not hasattr(ccxt_async, exchange_id):
        raise ValueError(f"Unsupported CCXT exchange: {exchange_id}")
    return getattr(ccxt_async, exchange_id)


class CCXTIngestionAdapter(IngestionAdapter):
    """Use CCXT's async support for market data ingestion."""

    def __init__(
        self,
        *,
        exchange_id: str = "binance",
        client_params: Optional[dict[str, Any]] = None,
        retry: Optional[RetryConfig] = None,
        rate_limit: Optional[RateLimitConfig] = None,
    ) -> None:
        super().__init__(retry=retry, rate_limit=rate_limit)
        factory = _load_exchange_factory(exchange_id)
        params = client_params or {"enableRateLimit": True}
        self._exchange = factory(params)
        self._exchange_id = exchange_id

    async def fetch(
        self,
        *,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 500,
        since: Optional[int] = None,
        instrument_type: InstrumentType = InstrumentType.SPOT,
    ) -> list[Ticker]:
        """Fetch OHLCV candles and convert them to tick-level close prices."""

        async def _call() -> list[list[float]]:
            return await self._exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, since=since, limit=limit
            )

        candles = await self._run_with_policy(_call)
        ticks: list[Ticker] = []
        for ts, _open, _high, _low, close, volume in candles:
            tick = Ticker.create(
                symbol=symbol,
                venue=self._exchange_id.upper(),
                price=close,
                volume=volume,
                instrument_type=instrument_type,
                timestamp=normalize_timestamp(ts / 1000 if ts > 1e12 else ts),
            )
            ticks.append(tick)
        logger.debug(
            "ccxt_fetch", exchange=self._exchange_id, symbol=symbol, count=len(ticks)
        )
        return ticks

    async def stream(
        self,
        *,
        symbol: str,
        venue: Optional[str] = None,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        ws_url: Optional[str] = None,
    ) -> AsyncIterator[Ticker]:
        """Stream live trades using the exchange websocket feed."""

        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - defensive guard
            raise RuntimeError("websockets must be installed for streaming") from exc

        venue_name = venue or self._exchange_id.upper()
        url = ws_url or f"wss://stream.binance.com:9443/ws/{symbol.lower()}@trade"
        attempt = 0

        while True:
            try:
                async with websockets.connect(
                    url, ping_interval=20, ping_timeout=20
                ) as ws:
                    attempt = 0
                    logger.info("ccxt_ws_connected", url=url, symbol=symbol)
                    while True:
                        payload = await self._run_with_policy(ws.recv)
                        data = json.loads(payload)
                        price = data.get("p") or data.get("price")
                        volume = data.get("q") or data.get("qty", 0)
                        trade_ts = data.get("T") or data.get("E") or data.get("ts")
                        if isinstance(trade_ts, str) and trade_ts.isdigit():
                            trade_ts = int(trade_ts)
                        if trade_ts is None:
                            trade_ts = time.time()
                        if isinstance(trade_ts, (int, float)) and trade_ts > 1e12:
                            trade_ts = trade_ts / 1000
                        tick = Ticker.create(
                            symbol=symbol,
                            venue=venue_name,
                            price=price,
                            volume=volume,
                            instrument_type=instrument_type,
                            timestamp=normalize_timestamp(trade_ts),
                        )
                        yield tick
            except Exception as exc:
                attempt += 1
                logger.warning(
                    "ccxt_ws_reconnect", url=url, attempt=attempt, error=str(exc)
                )
                await self._sleep_backoff(attempt)

    async def aclose(self) -> None:
        if hasattr(self._exchange, "close"):
            await self._exchange.close()
