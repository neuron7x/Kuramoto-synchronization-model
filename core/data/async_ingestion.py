# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Async data ingestion APIs for TradePulse with strict path validation."""
from __future__ import annotations

import asyncio
import csv
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import InvalidOperation
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    Iterable,
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

__all__ = [
    "AsyncDataIngestor",
    "AsyncWebSocketStream",
    "BinanceWebSocketStream",
    "Ticker",
    "merge_streams",
]

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


def _iter_csv_chunks(
    path: Path,
    *,
    symbol: str,
    venue: str,
    instrument_type: InstrumentType,
    market: Optional[str],
    chunk_size: int,
    required_fields: Iterable[str] | None,
    timestamp_field: str,
    price_field: str,
    volume_field: str,
) -> Iterable[list[Ticker]]:
    """Yield parsed CSV ticks in fixed-size batches."""

    resolved_chunk_size = max(1, int(chunk_size))

    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames is None:
            raise ValueError("CSV file must include a header row")

        required = set(required_fields or ())
        required.update({timestamp_field, price_field})
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV missing columns: {', '.join(sorted(missing))}")

        chunk: list[Ticker] = []

        for row_number, row in enumerate(reader, start=2):
            try:
                ts_raw = float(row[timestamp_field])
                price = row[price_field]
                volume = row.get(volume_field, 0.0) or 0.0

                tick = Ticker.create(
                    symbol=symbol,
                    venue=venue,
                    price=price,
                    timestamp=normalize_timestamp(ts_raw, market=market),
                    volume=volume,
                    instrument_type=instrument_type,
                )
                chunk.append(tick)

                if len(chunk) >= resolved_chunk_size:
                    yield chunk
                    chunk = []

            except (TypeError, ValueError, InvalidOperation) as exc:
                logger.warning(
                    f"Skipping malformed row {row_number}",
                    path=str(path),
                    error=str(exc),
                )
                continue

        if chunk:
            yield chunk


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
        required_fields: Iterable[str] | None = None,
        timestamp_field: str = "ts",
        price_field: str = "price",
        volume_field: str = "volume",
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
            required_fields: Additional CSV columns that must be present
            timestamp_field: Column containing the timestamp values
            price_field: Column containing the price values
            volume_field: Column containing the volume values

        Yields:
            Ticker objects from CSV

        Raises:
            ValueError: If CSV is missing required columns
        """
        resolved_path = self._path_guard.resolve(path, description="CSV data file")

        queue: asyncio.Queue[object] = asyncio.Queue(maxsize=1)
        sentinel = object()
        loop = asyncio.get_running_loop()

        def _producer() -> None:
            def _enqueue(item: object) -> None:
                coro = queue.put(item)
                try:
                    fut = asyncio.run_coroutine_threadsafe(coro, loop)
                    fut.result()
                except asyncio.CancelledError:  # pragma: no cover - consumer cancelled
                    return
                except RuntimeError:  # pragma: no cover - loop closed
                    coro.close()
                    return

            try:
                for chunk in _iter_csv_chunks(
                    resolved_path,
                    symbol=symbol,
                    venue=venue,
                    instrument_type=instrument_type,
                    market=market,
                    chunk_size=chunk_size,
                    required_fields=required_fields,
                    timestamp_field=timestamp_field,
                    price_field=price_field,
                    volume_field=volume_field,
                ):
                    _enqueue(chunk)
            except Exception as exc:  # pragma: no cover - propagated to consumer
                _enqueue(exc)
            finally:
                _enqueue(sentinel)

        worker_task = asyncio.create_task(asyncio.to_thread(_producer))

        with logger.operation("async_csv_read", path=str(resolved_path), symbol=symbol):
            try:
                with _TickMetricBatcher(
                    metrics,
                    "csv",
                    symbol,
                    flush_threshold=max(1, chunk_size),
                ) as metric_batcher:
                    while True:
                        item = await queue.get()

                        if item is sentinel:
                            break

                        if isinstance(item, Exception):
                            raise item

                        if not isinstance(item, list):
                            raise TypeError(
                                f"Unexpected payload type from CSV producer: {type(item)!r}"
                            )

                        chunk = item
                        consumed = 0
                        try:
                            for tick in chunk:
                                yield tick
                                consumed += 1
                        finally:
                            if consumed:
                                metric_batcher.add(consumed)

                        if delay_ms > 0:
                            await asyncio.sleep(delay_ms / 1000.0)

            except Exception as exc:
                logger.error(
                    "CSV ingestion failed", path=str(resolved_path), error=str(exc)
                )
                raise
            finally:
                if not worker_task.done():
                    worker_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await worker_task
                else:
                    # Ensure any exception is observed to avoid "exception was never retrieved" warnings.
                    worker_task.exception()

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
            with (
                logger.operation(
                    "async_stream_ticks", source=source, symbol=symbol, mode="connector"
                ),
                _TickMetricBatcher(metrics, source, symbol) as metric_batcher,
            ):
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
        with (
            logger.operation(
                "async_stream_ticks", source=source, symbol=symbol, mode="synthetic"
            ),
            _TickMetricBatcher(metrics, source, symbol) as metric_batcher,
        ):
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


class BinanceWebSocketStream(AsyncWebSocketStream):
    """Async WebSocket stream for Binance exchange.

    This implementation connects to Binance WebSocket API and streams
    real-time trade data as Ticker objects.

    Example:
        >>> stream = BinanceWebSocketStream("BTCUSDT")
        >>> await stream.connect()
        >>> async for tick in stream.subscribe():
        ...     print(f"Price: {tick.price}")
        >>> await stream.disconnect()
    """

    BINANCE_WS_BASE_URL = "wss://stream.binance.com:9443/ws"

    def __init__(
        self,
        symbol: str,
        *,
        url: Optional[str] = None,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        reconnect_attempts: int = 5,
        reconnect_delay: float = 1.0,
    ):
        """Initialize Binance WebSocket stream.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            url: Custom WebSocket URL (defaults to Binance production stream)
            instrument_type: Instrument type (SPOT or FUTURES)
            reconnect_attempts: Number of reconnection attempts before giving up
            reconnect_delay: Base delay between reconnection attempts in seconds
        """
        stream_url = url or f"{self.BINANCE_WS_BASE_URL}/{symbol.lower()}@trade"
        super().__init__(stream_url, symbol)
        self._instrument_type = instrument_type
        self._reconnect_attempts = reconnect_attempts
        self._reconnect_delay = reconnect_delay
        self._websocket: Any = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Connect to Binance WebSocket.

        Raises:
            RuntimeError: If websockets library is not installed
            ConnectionError: If connection fails after all retry attempts
        """
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError(
                "websockets library is required for BinanceWebSocketStream. "
                "Install it with: pip install websockets"
            ) from exc

        async with self._lock:
            if self._websocket is not None and self._running:
                return

            attempt = 0
            last_error: Optional[Exception] = None

            while attempt < self._reconnect_attempts:
                try:
                    self._websocket = await websockets.connect(
                        self.url,
                        ping_interval=20,
                        ping_timeout=20,
                        close_timeout=5,
                    )
                    self._running = True
                    logger.info(
                        "binance_ws_connected",
                        url=self.url,
                        symbol=self.symbol,
                    )
                    return
                except Exception as exc:
                    attempt += 1
                    last_error = exc
                    logger.warning(
                        "binance_ws_connect_retry",
                        url=self.url,
                        attempt=attempt,
                        max_attempts=self._reconnect_attempts,
                        error=str(exc),
                    )
                    if attempt < self._reconnect_attempts:
                        await asyncio.sleep(self._reconnect_delay * attempt)

            raise ConnectionError(
                f"Failed to connect to Binance WebSocket after "
                f"{self._reconnect_attempts} attempts: {last_error}"
            )

    async def disconnect(self) -> None:
        """Disconnect from Binance WebSocket."""
        async with self._lock:
            self._running = False
            if self._websocket is not None:
                with suppress(Exception):
                    await self._websocket.close()
                self._websocket = None
                logger.info(
                    "binance_ws_disconnected",
                    url=self.url,
                    symbol=self.symbol,
                )

    async def subscribe(self) -> AsyncIterator[Ticker]:
        """Subscribe to Binance trade stream.

        Yields:
            Ticker objects from the WebSocket stream

        Raises:
            RuntimeError: If not connected
        """
        if not self._running or self._websocket is None:
            raise RuntimeError(
                "WebSocket not connected. Call connect() before subscribe()."
            )

        import json

        attempt = 0
        while self._running:
            try:
                message = await self._websocket.recv()
                attempt = 0  # Reset on successful receive

                try:
                    data = json.loads(message)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "binance_ws_invalid_json",
                        symbol=self.symbol,
                        error=str(exc),
                    )
                    continue

                # Parse Binance trade message format
                tick = self._parse_trade_message(data)
                if tick is not None:
                    yield tick

            except asyncio.CancelledError:
                break
            except Exception as exc:
                if not self._running:
                    break

                attempt += 1
                logger.warning(
                    "binance_ws_recv_error",
                    symbol=self.symbol,
                    attempt=attempt,
                    error=str(exc),
                )

                if attempt >= self._reconnect_attempts:
                    logger.error(
                        "binance_ws_max_retries_exceeded",
                        symbol=self.symbol,
                        attempts=attempt,
                    )
                    break

                # Attempt reconnection
                try:
                    await self.disconnect()
                    await asyncio.sleep(self._reconnect_delay * attempt)
                    await self.connect()
                except Exception as reconnect_exc:
                    logger.error(
                        "binance_ws_reconnect_failed",
                        symbol=self.symbol,
                        error=str(reconnect_exc),
                    )
                    break

    def _parse_trade_message(self, data: Mapping[str, Any]) -> Optional[Ticker]:
        """Parse a Binance trade WebSocket message into a Ticker.

        Args:
            data: Parsed JSON message from Binance WebSocket

        Returns:
            Ticker object or None if message cannot be parsed
        """
        # Binance trade message format:
        # {
        #   "e": "trade",
        #   "E": event_time,
        #   "s": symbol,
        #   "p": price,
        #   "q": quantity,
        #   "T": trade_time
        # }
        try:
            event_type = data.get("e")
            if event_type != "trade":
                return None

            price_str = data.get("p")
            quantity_str = data.get("q")
            trade_time = data.get("T")

            if price_str is None or trade_time is None:
                logger.warning(
                    "binance_ws_incomplete_trade",
                    symbol=self.symbol,
                    data=data,
                )
                return None

            price = float(price_str)
            volume = float(quantity_str) if quantity_str else 0.0

            # Binance timestamps are in milliseconds
            ts_seconds = trade_time / 1000 if trade_time > 1e12 else trade_time
            timestamp = normalize_timestamp(ts_seconds)

            return Ticker.create(
                symbol=self.symbol,
                venue="BINANCE",
                price=price,
                volume=volume,
                timestamp=timestamp,
                instrument_type=self._instrument_type,
            )
        except (TypeError, ValueError, KeyError) as exc:
            logger.warning(
                "binance_ws_parse_error",
                symbol=self.symbol,
                error=str(exc),
                data=data,
            )
            return None


async def merge_streams(*streams: AsyncIterator[Ticker]) -> AsyncIterator[Ticker]:
    """Merge multiple async tick streams into one resilient iterator.

    Args:
        *streams: Variable number of async iterators

    Yields:
        Ticks from all streams in arrival order, skipping streams that fail.
    """

    # Bound the shared queue so that each stream can only prefetch a limited
    # number of ticks. This prevents a fast or stalled stream from buffering an
    # unbounded number of items when the downstream consumer is slow, while
    # still allowing a small amount of ahead-of-time reads for fairness.
    prefetch_per_stream = 2
    max_queue_size = max(1, len(streams) * prefetch_per_stream)

    @dataclass(frozen=True, slots=True)
    class _StreamError:
        stream: str | None
        exception: Exception

    queue: asyncio.Queue[tuple[int, Ticker | None | _StreamError]] = asyncio.Queue(
        maxsize=max_queue_size
    )

    async def _pump(index: int, stream: AsyncIterator[Ticker]) -> None:
        symbol = getattr(stream, "symbol", None)
        try:
            while True:
                try:
                    tick = await asyncio.shield(anext(stream))
                except StopAsyncIteration:
                    break
                except Exception as exc:
                    logger.warning(
                        "Async stream terminated with error",
                        stream=symbol,
                        error=str(exc),
                        exc_info=exc,
                    )
                    await asyncio.shield(queue.put((index, _StreamError(symbol, exc))))
                    break
                await queue.put((index, tick))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Async stream pump failed",
                stream=symbol,
                error=str(exc),
                exc_info=exc,
            )
            await asyncio.shield(queue.put((index, _StreamError(symbol, exc))))
        finally:
            try:
                await asyncio.shield(queue.put((index, None)))
            except Exception:
                pass
            aclose = getattr(stream, "aclose", None)
            if callable(aclose):
                with suppress(Exception):
                    await asyncio.shield(aclose())

    workers = [
        asyncio.create_task(_pump(idx, stream)) for idx, stream in enumerate(streams)
    ]

    remaining = len(workers)
    try:
        while remaining:
            _, item = await queue.get()
            if isinstance(item, _StreamError):
                logger.warning(
                    "Async stream terminated with error",
                    stream=item.stream,
                    error=str(item.exception),
                    exc_info=item.exception,
                )
                continue
            if item is None:
                remaining -= 1
                continue
            yield item
    finally:
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        while True:
            try:
                _, item = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if isinstance(item, _StreamError):
                logger.warning(
                    "Async stream terminated with error",
                    stream=item.stream,
                    error=str(item.exception),
                    exc_info=item.exception,
                )


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
