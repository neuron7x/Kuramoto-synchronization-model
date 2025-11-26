# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Data ingestion infrastructure for market data and price feeds.

This module provides the core data ingestion pipeline for TradePulse, handling:
- Real-time streaming data from exchanges (Binance, Alpaca, etc.)
- Historical data loading from CSV and other formats
- Data normalization and timestamp handling
- Path validation and security controls
- Robust error handling and retry logic

The ingestion system is designed to be resilient, performant, and type-safe,
with full observability through OpenTelemetry tracing.

Example:
    >>> from core.data.ingestion import DataIngestor
    >>> ingestor = DataIngestor()
    >>> tickers = ingestor.load_csv("data/BTCUSDT.csv")
"""
from __future__ import annotations

import csv
import logging
from decimal import InvalidOperation
from pathlib import Path
from typing import Callable, Iterable, Optional

try:
    from binance.websocket.spot.websocket_client import SpotWebsocketClient as BinanceWS
except Exception:  # pragma: no cover - optional dependency
    BinanceWS = None

from core.data.models import InstrumentType
from core.data.models import PriceTick as Ticker
from core.data.path_guard import DataPathGuard
from core.data.timeutils import normalize_timestamp
from interfaces.ingestion import DataIngestionService
from observability.tracing import pipeline_span

logger = logging.getLogger(__name__)

__all__ = ["Ticker", "DataIngestor", "BinanceStreamHandle"]


class BinanceStreamHandle:
    def __init__(self, ws: BinanceWS) -> None:
        self._ws = ws
        self._active = False

    def start(
        self, *, symbol: str, interval: str, callback: Callable[[dict], None]
    ) -> None:
        self._active = True
        self._ws.start()
        self._ws.kline(
            symbol=symbol.lower(), id=1, interval=interval, callback=callback
        )

    def close(self) -> None:
        if self._active:
            self._ws.stop()
            self._active = False

    def __enter__(self) -> "BinanceStreamHandle":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class DataIngestor(DataIngestionService):
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        *,
        allowed_roots: Iterable[str | Path] | None = None,
        max_csv_bytes: Optional[int] = None,
        follow_symlinks: bool = False,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self._path_guard = DataPathGuard(
            allowed_roots=allowed_roots,
            max_bytes=max_csv_bytes,
            follow_symlinks=follow_symlinks,
        )

    def historical_csv(
        self,
        path: str,
        on_tick: Callable[[Ticker], None],
        *,
        required_fields: Iterable[str] | None = None,
        timestamp_field: str = "ts",
        price_field: str = "price",
        volume_field: str = "volume",
        symbol: str = "UNKNOWN",
        venue: str = "CSV",
        instrument_type: InstrumentType = InstrumentType.SPOT,
        market: Optional[str] = None,
    ) -> None:
        missing: list[str] = []
        resolved_path = self._path_guard.resolve(path, description="CSV data file")

        with pipeline_span(
            "ingest.historical_csv",
            source="csv",
            path=str(resolved_path),
            symbol=symbol,
            venue=venue,
        ):
            with resolved_path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    raise ValueError("CSV file must include a header row")
                required = set(required_fields or ())
                required.update({timestamp_field, price_field})
                missing = [
                    field
                    for field in sorted(required)
                    if field not in reader.fieldnames
                ]
                if missing:
                    raise ValueError(
                        f"CSV missing required columns: {', '.join(missing)}"
                    )
                for row_number, row in enumerate(reader, start=2):
                    try:
                        ts_raw = float(row[timestamp_field])
                        price = row[price_field]
                        volume = row.get(volume_field, 0.0) or 0.0
                        timestamp = normalize_timestamp(ts_raw, market=market)
                        tick = Ticker.create(
                            symbol=symbol,
                            venue=venue,
                            price=price,
                            timestamp=timestamp,
                            volume=volume,
                            instrument_type=instrument_type,
                        )
                    except (TypeError, ValueError, InvalidOperation) as exc:
                        logger.warning(
                            "Skipping malformed row %s in %s: %s", row_number, path, exc
                        )
                        continue
                    on_tick(tick)

    def binance_ws(
        self, symbol: str, on_tick: Callable[[Ticker], None], *, interval: str = "1m"
    ) -> object:
        if BinanceWS is None:
            raise RuntimeError("python-binance is not installed")

        ws = BinanceWS()
        handle = BinanceStreamHandle(ws)

        def _callback(message: dict) -> None:
            kline = message.get("k")
            if not kline:
                return
            try:
                ts = normalize_timestamp(float(kline["T"]) / 1000.0, market="BINANCE")
                tick = Ticker.create(
                    symbol=symbol,
                    venue="BINANCE",
                    price=kline["c"],
                    timestamp=ts,
                    volume=kline.get("v", 0.0),
                    instrument_type=InstrumentType.SPOT,
                )
            except (TypeError, ValueError, InvalidOperation) as exc:
                logger.warning("Failed to parse websocket payload: %s", exc)
                return
            on_tick(tick)

        with pipeline_span(
            "ingest.live_stream",
            source="binance",
            symbol=symbol,
            interval=interval,
        ):
            handle.start(symbol=symbol, interval=interval, callback=_callback)
        setattr(ws, "stream_handle", handle)
        return ws
