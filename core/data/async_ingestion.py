# SPDX-License-Identifier: MIT
"""Async data ingestion APIs for TradePulse with strict path validation."""
from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timezone
from decimal import InvalidOperation
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
)

from core.data.connectors.market import BaseMarketDataConnector
from core.data.models import InstrumentType
from core.data.models import PriceTick as Ticker
from core.data.path_guard import DataPathGuard
from core.data.timeutils import normalize_timestamp
from core.utils.logging import get_logger
from core.utils.metrics import get_metrics_collector
from interfaces.ingestion import AsyncDataIngestionService

if TYPE_CHECKING:
    from core.events import TickEvent

__all__ = ["AsyncDataIngestor", "AsyncWebSocketStream", "Ticker", "merge_streams"]

logger = get_logger(__name__)
metrics = get_metrics_collector()


class _TickMetricBatcher:
    """Accumulate tick metrics and flush in batches to reduce contention."""

    __slots__ = ("_collector", "_source", "_symbol", "_flush_threshold", "_pending")

    def __init__(
        self,
        collector: Any,
        source: str,
        symbol: str,
        *,
        flush_threshold: int = 256,
    ) -> None:
        self._collector = collector
        self._source = source
        self._symbol = symbol
        self._flush_threshold = max(1, int(flush_threshold))
        self._pending = 0

    def __enter__(self) -> "_TickMetricBatcher":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.flush()
        return False

    def add(self, count: int = 1) -> None:
        """Record ``count`` processed ticks, flushing when the threshold is hit."""

        if count <= 0:
            return
        self._pending += count
        if self._pending >= self._flush_threshold:
            self._flush_pending()

    def flush(self) -> None:
        """Flush any buffered increments to the metrics collector."""

        self._flush_pending()

    def _flush_pending(self) -> None:
        pending = self._pending
        if pending <= 0:
            return
        record = getattr(self._collector, "record_tick_processed", None)
        if record is None:
            self._pending = 0
            return
        record(self._source, self._symbol, pending)
        self._pending = 0


ConnectorFactory = Callable[[], BaseMarketDataConnector]
ConnectorEntry = BaseMarketDataConnector | ConnectorFactory


class AsyncDataIngestor(AsyncDataIngestionService):
    """Async data ingestion with support for CSV and streaming sources."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        *,
        allowed_roots: Iterable[str | Path] | None = None,
        max_csv_bytes: Optional[int] = None,
        follow_symlinks: bool = False,
        market_connectors: Mapping[str, ConnectorEntry] | None = None,
    ):
        """Initialize async data ingestor.

        Args:
            api_key: Optional API key for authenticated sources
            api_secret: Optional API secret for authenticated sources
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self._path_guard = DataPathGuard(
            allowed_roots=allowed_roots,
            max_bytes=max_csv_bytes,
            follow_symlinks=follow_symlinks,
        )
        self._market_connectors: dict[str, ConnectorEntry] = {}
        if market_connectors:
            for name, connector in market_connectors.items():
                key = name.lower()
                self._market_connectors[key] = connector

    async def read_csv(
        self,
        path: str,
        *,
        symbol: str = "UNKNOWN",
        venue: str = "CSV",
        instrument_type: InstrumentType = InstrumentType.SPOT,
        market: Optional[str] = None,
        chunk_size: int = 1000,
        delay_ms: int = 0,
    ) -> AsyncIterator[Ticker]:
        """Async CSV reader that yields ticks.

        Args:
            path: Path to CSV file
            symbol: Trading symbol for the data
            venue: Name of the data venue (used for metadata)
            instrument_type: Instrument classification (spot or futures)
            market: Optional market calendar identifier for timezone normalization
            chunk_size: Number of rows to read at a time
            delay_ms: Optional delay between chunks (for simulation)

        Yields:
            Ticker objects from CSV

        Raises:
            ValueError: If CSV is missing required columns
        """
        resolved_path = self._path_guard.resolve(path, description="CSV data file")

        with logger.operation("async_csv_read", path=str(resolved_path), symbol=symbol):
            try:
                with resolved_path.open("r", encoding="utf-8") as f, _TickMetricBatcher(
                    metrics,
                    "csv",
                    symbol,
                    flush_threshold=max(1, chunk_size),
                ) as metric_batcher:
                    reader = csv.DictReader(f)

                    if reader.fieldnames is None:
                        raise ValueError("CSV file must include a header row")

                    required = {"ts", "price"}
                    missing = required - set(reader.fieldnames)
                    if missing:
                        raise ValueError(f"CSV missing columns: {', '.join(missing)}")

                    chunk: List[Ticker] = []
                    for row_number, row in enumerate(reader, start=2):
                        try:
                            ts_raw = float(row["ts"])
                            price = row["price"]
                            volume = row.get("volume", 0.0) or 0.0

                            tick = Ticker.create(
                                symbol=symbol,
                                venue=venue,
                                price=price,
                                timestamp=normalize_timestamp(ts_raw, market=market),
                                volume=volume,
                                instrument_type=instrument_type,
                            )
                            chunk.append(tick)

                            if len(chunk) >= chunk_size:
                                consumed = 0
                                try:
                                    for tick in chunk:
                                        yield tick
                                        consumed += 1
                                finally:
                                    if consumed:
                                        metric_batcher.add(consumed)
                                chunk = []

                                if delay_ms > 0:
                                    await asyncio.sleep(delay_ms / 1000.0)

                        except (TypeError, ValueError, InvalidOperation) as exc:
                            logger.warning(
                                f"Skipping malformed row {row_number}",
                                path=path,
                                error=str(exc),
                            )
                            continue

                    # Yield remaining ticks
                    if chunk:
                        consumed = 0
                        try:
                            for tick in chunk:
                                yield tick
                                consumed += 1
                        finally:
                            if consumed:
                                metric_batcher.add(consumed)

            except Exception as exc:
                logger.error("CSV ingestion failed", path=path, error=str(exc))
                raise

    async def stream_ticks(
        self,
        source: str,
        symbol: str,
        *,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        interval_ms: int = 1000,
        max_ticks: Optional[int] = None,
    ) -> AsyncIterator[Ticker]:
        """Stream ticks from a live source.

        Args:
            source: Data source name
            symbol: Trading symbol
            instrument_type: Instrument classification (spot or futures)
            interval_ms: Polling interval in milliseconds
            max_ticks: Optional maximum number of ticks to yield

        Yields:
            Ticker objects from the stream
        """
        connector, should_close = self._resolve_market_connector(source)
        if connector is None:
            async for tick in self._stream_synthetic(
                source,
                symbol,
                instrument_type=instrument_type,
                interval_ms=interval_ms,
                max_ticks=max_ticks,
            ):
                yield tick
            return

        count = 0
        try:
            with logger.operation(
                "async_stream_ticks", source=source, symbol=symbol, mode="connector"
            ), _TickMetricBatcher(metrics, source, symbol) as metric_batcher:
                async for event in connector.stream_ticks(
                    symbol=symbol, instrument_type=instrument_type
                ):
                    tick = _tick_event_to_price_tick(
                        event,
                        venue=source.upper(),
                        instrument_type=instrument_type,
                    )
                    yield tick
                    metric_batcher.add()
                    count += 1
                    if max_ticks is not None and count >= max_ticks:
                        return
        finally:
            if should_close:
                await connector.aclose()

    async def batch_process(
        self,
        ticks: AsyncIterator[Ticker],
        callback: Callable[[list[Ticker]], None],
        batch_size: int = 100,
    ) -> int:
        """Process ticks in batches with async callback.

        Args:
            ticks: Async iterator of ticks
            callback: Function to call with each batch
            batch_size: Number of ticks per batch

        Returns:
            Total number of ticks processed
        """
        batch: list[Ticker] = []
        total = 0

        async for tick in ticks:
            batch.append(tick)
            total += 1

            if len(batch) >= batch_size:
                callback(batch)
                batch = []

        # Process remaining ticks
        if batch:
            callback(batch)

        return total

    async def fetch_market_snapshot(
        self,
        source: str,
        *,
        symbol: str,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        **kwargs: Any,
    ) -> list[Ticker]:
        """Fetch a bounded snapshot of ticks from a configured market connector."""

        connector, should_close = self._resolve_market_connector(source)
        if connector is None:
            raise ValueError(
                f"No market data connector configured for source '{source}'"
            )

        params = dict(kwargs)
        params.setdefault("symbol", symbol)
        params.setdefault("instrument_type", instrument_type)

        try:
            with logger.operation("async_fetch_snapshot", source=source, symbol=symbol):
                events = await connector.fetch_snapshot(**params)
        finally:
            if should_close:
                await connector.aclose()

        ticks: list[Ticker] = []
        processed = 0
        for event in events:
            tick = _tick_event_to_price_tick(
                event,
                venue=source.upper(),
                instrument_type=instrument_type,
            )
            ticks.append(tick)
            processed += 1
        if processed:
            metrics.record_tick_processed(source, symbol, processed)
        return ticks

    def _resolve_market_connector(
        self, source: str
    ) -> Tuple[Optional[BaseMarketDataConnector], bool]:
        entry = self._market_connectors.get(source.lower())
        if entry is None:
            return None, False
        if callable(entry):
            connector = entry()
            if not isinstance(connector, BaseMarketDataConnector):
                raise TypeError(
                    "Connector factory must return a BaseMarketDataConnector instance"
                )
            return connector, True
        return entry, False

    async def _stream_synthetic(
        self,
        source: str,
        symbol: str,
        *,
        instrument_type: InstrumentType,
        interval_ms: int,
        max_ticks: Optional[int],
    ) -> AsyncIterator[Ticker]:
        with logger.operation(
            "async_stream_ticks", source=source, symbol=symbol, mode="synthetic"
        ), _TickMetricBatcher(metrics, source, symbol) as metric_batcher:
            count = 0

            while max_ticks is None or count < max_ticks:
                await asyncio.sleep(interval_ms / 1000.0)

                tick = Ticker.create(
                    symbol=symbol,
                    venue=source.upper(),
                    price=100.0 + (count % 10),
                    timestamp=normalize_timestamp(datetime.now(timezone.utc)),
                    volume=1000.0,
                    instrument_type=instrument_type,
                )

                yield tick
                metric_batcher.add()
                count += 1


class AsyncWebSocketStream:
    """Async WebSocket stream handler (base class for exchange-specific implementations)."""

    def __init__(self, url: str, symbol: str):
        """Initialize WebSocket stream.

        Args:
            url: WebSocket URL
            symbol: Trading symbol to subscribe to
        """
        self.url = url
        self.symbol = symbol
        self._running = False

    async def connect(self) -> None:
        """Connect to WebSocket (to be implemented by subclasses)."""
        raise NotImplementedError

    async def disconnect(self) -> None:
        """Disconnect from WebSocket (to be implemented by subclasses)."""
        raise NotImplementedError

    async def subscribe(self) -> AsyncIterator[Ticker]:
        """Subscribe to tick updates (to be implemented by subclasses).

        Yields:
            Ticker objects from WebSocket
        """
        raise NotImplementedError


async def merge_streams(*streams: AsyncIterator[Ticker]) -> AsyncIterator[Ticker]:
    """Merge multiple async tick streams into one resilient iterator.

    Args:
        *streams: Variable number of async iterators

    Yields:
        Ticks from all streams in arrival order, skipping streams that fail.
    """

    pending_tasks: dict[Any, AsyncIterator[Ticker]] = {}

    for stream in streams:
        task = asyncio.create_task(anext(stream))  # type: ignore[arg-type]
        pending_tasks[task] = stream

    while pending_tasks:
        done, _ = await asyncio.wait(
            pending_tasks.keys(),
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            stream = pending_tasks.pop(task)

            try:
                tick = task.result()
            except StopAsyncIteration:
                # Stream exhausted, do not reschedule.
                continue
            except Exception as exc:
                logger.warning(
                    "Async stream terminated with error",
                    stream=getattr(stream, "symbol", None),
                    error=str(exc),
                )
                continue

            yield tick

            next_task = asyncio.create_task(anext(stream))  # type: ignore[arg-type]
            pending_tasks[next_task] = stream


__all__ = [
    "Ticker",
    "AsyncDataIngestor",
    "AsyncWebSocketStream",
    "merge_streams",
]


def _tick_event_to_price_tick(
    event: TickEvent,
    *,
    venue: str,
    instrument_type: InstrumentType,
) -> Ticker:
    from core.events import (
        TickEvent,  # Local import to avoid circular dependencies at module import time
    )

    if not isinstance(event, TickEvent):
        raise TypeError("Expected TickEvent from connector stream")

    price = event.last_price or event.bid_price or event.ask_price
    if price is None:
        raise ValueError("TickEvent is missing price information")

    timestamp = datetime.fromtimestamp(event.timestamp / 1_000_000, tz=timezone.utc)
    volume = event.volume or 0
    tick = Ticker.create(
        symbol=event.symbol,
        venue=venue,
        price=price,
        timestamp=timestamp,
        volume=volume,
        instrument_type=instrument_type,
    )
    return tick
