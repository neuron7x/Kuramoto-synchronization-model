"""Tests for async data ingestion."""

import asyncio
import csv
import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Iterable, List

import pytest

from core.data.adapters.base import IngestionAdapter
from core.data.async_ingestion import AsyncDataIngestor, Ticker, merge_streams
from core.data.connectors.market import BaseMarketDataConnector
from core.data.models import InstrumentType
from tests.tolerances import FLOAT_ABS_TOL, FLOAT_REL_TOL


class DummyAdapter(IngestionAdapter):
    """Adapter returning predetermined ticks for deterministic testing."""

    def __init__(self, ticks: Iterable[Ticker]) -> None:
        super().__init__()
        self._ticks: List[Ticker] = list(ticks)
        self.closed = False

    async def fetch(self, **kwargs):  # type: ignore[override]
        return list(self._ticks)

    async def stream(self, **kwargs):  # type: ignore[override]
        for tick in self._ticks:
            yield tick

    async def aclose(self) -> None:  # type: ignore[override]
        self.closed = True


class TestAsyncDataIngestor:
    """Test async data ingestion functionality."""

    @pytest.mark.asyncio
    async def test_read_csv_basic(self, tmp_path: Path) -> None:
        """Test basic CSV reading."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("ts,price,volume\n1.0,100.0,1000\n2.0,101.0,2000\n")

        ingestor = AsyncDataIngestor()
        ticks = []

        async for tick in ingestor.read_csv(str(csv_file), symbol="TEST", venue="TEST"):
            ticks.append(tick)

        assert len(ticks) == 2
        assert ticks[0].price == 100.0
        assert ticks[1].price == 101.0
        assert ticks[0].symbol == "TEST"

    @pytest.mark.asyncio
    async def test_read_csv_chunked(self, tmp_path: Path) -> None:
        """Test CSV reading with chunks."""
        csv_file = tmp_path / "test.csv"

        # Create CSV with 10 rows
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["ts", "price", "volume"])
            for i in range(10):
                writer.writerow([float(i), 100.0 + i, 1000])

        ingestor = AsyncDataIngestor()
        ticks = []

        async for tick in ingestor.read_csv(str(csv_file), chunk_size=3):
            ticks.append(tick)

        assert len(ticks) == 10
        assert ticks[5].price == 105.0

    @pytest.mark.asyncio
    async def test_read_csv_missing_columns(self, tmp_path: Path) -> None:
        """Test CSV with missing required columns."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("timestamp,value\n1.0,100.0\n")

        ingestor = AsyncDataIngestor()

        with pytest.raises(ValueError, match="missing columns"):
            async for _ in ingestor.read_csv(str(csv_file)):
                pass

    @pytest.mark.asyncio
    async def test_read_csv_custom_columns(self, tmp_path: Path) -> None:
        """Custom column names should be supported for CSV ingestion."""
        csv_file = tmp_path / "test_custom.csv"
        csv_file.write_text(
            "timestamp,close,qty\n1.0,100.0,10\n2.0,101.5,20\n",
            encoding="utf-8",
        )

        ingestor = AsyncDataIngestor()
        ticks: list[Ticker] = []

        async for tick in ingestor.read_csv(
            str(csv_file),
            timestamp_field="timestamp",
            price_field="close",
            volume_field="qty",
        ):
            ticks.append(tick)

        assert [tick.price for tick in ticks] == [100.0, 101.5]
        assert [tick.volume for tick in ticks] == [10.0, 20.0]

    @pytest.mark.asyncio
    async def test_stream_ticks_basic(self) -> None:
        """Test basic tick streaming."""
        ingestor = AsyncDataIngestor()
        ticks = []

        async for tick in ingestor.stream_ticks(
            "test_source", "BTC", interval_ms=10, max_ticks=5
        ):
            ticks.append(tick)

        assert len(ticks) == 5
        assert all(tick.symbol == "BTC" for tick in ticks)

    @pytest.mark.asyncio
    async def test_stream_ticks_with_market_connector(self) -> None:
        """Configured connectors should drive the live feed instead of the simulator."""

        ticks = [
            Ticker.create(
                symbol="BTCUSDT",
                venue="BINANCE",
                price=100.0,
                timestamp=datetime.fromtimestamp(1700000000, tz=timezone.utc),
                volume=1.0,
                instrument_type=InstrumentType.SPOT,
            ),
            Ticker.create(
                symbol="BTCUSDT",
                venue="BINANCE",
                price=101.0,
                timestamp=datetime.fromtimestamp(1700000060, tz=timezone.utc),
                volume=2.0,
                instrument_type=InstrumentType.SPOT,
            ),
        ]

        adapters: list[DummyAdapter] = []

        def factory() -> BaseMarketDataConnector:
            adapter = DummyAdapter(ticks)
            adapters.append(adapter)
            return BaseMarketDataConnector(adapter)

        ingestor = AsyncDataIngestor(market_connectors={"binance": factory})
        received: list[Ticker] = []

        async for tick in ingestor.stream_ticks(
            "binance",
            "BTCUSDT",
            max_ticks=2,
        ):
            received.append(tick)

        assert [float(tick.price) for tick in received] == [100.0, 101.0]
        assert all(tick.instrument_type is InstrumentType.SPOT for tick in received)
        assert adapters and all(adapter.closed for adapter in adapters)

    @pytest.mark.asyncio
    async def test_stream_ticks_with_reused_connector(self) -> None:
        """Pre-created connectors should remain open after streaming completes."""

        ticks = [
            Ticker.create(
                symbol="ETHUSD",
                venue="COINBASE",
                price=2000.0,
                timestamp=datetime.fromtimestamp(1700000000, tz=timezone.utc),
                volume=3.0,
                instrument_type=InstrumentType.SPOT,
            )
        ]

        adapter = DummyAdapter(ticks)
        connector = BaseMarketDataConnector(adapter)
        ingestor = AsyncDataIngestor(market_connectors={"coinbase": connector})

        async for _ in ingestor.stream_ticks("coinbase", "ETHUSD", max_ticks=1):
            break

        assert adapter.closed is False

    @pytest.mark.asyncio
    async def test_batch_process(self, tmp_path: Path) -> None:
        """Test batch processing of ticks."""
        csv_file = tmp_path / "test.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["ts", "price", "volume"])
            for i in range(25):
                writer.writerow([float(i), 100.0 + i, 1000])

        ingestor = AsyncDataIngestor()
        batches = []

        def collect_batch(batch):
            batches.append(len(batch))

        ticks_iter = ingestor.read_csv(str(csv_file))
        total = await ingestor.batch_process(ticks_iter, collect_batch, batch_size=10)

        assert total == 25
        assert len(batches) == 3  # 10 + 10 + 5
        assert batches[0] == 10
        assert batches[1] == 10
        assert batches[2] == 5

    @pytest.mark.asyncio
    async def test_read_csv_respects_allowed_roots(self, tmp_path: Path) -> None:
        """The async ingestor should reject paths outside the configured roots."""

        csv_file = tmp_path / "outside.csv"
        csv_file.write_text("ts,price\n1,1\n", encoding="utf-8")
        allowed_root = tmp_path / "allowed"
        allowed_root.mkdir()

        ingestor = AsyncDataIngestor(allowed_roots=[allowed_root])

        with pytest.raises(PermissionError):
            async for _ in ingestor.read_csv(str(csv_file)):
                pass

    @pytest.mark.asyncio
    async def test_read_csv_respects_size_limit(self, tmp_path: Path) -> None:
        """The async ingestor should enforce configured file size limits."""

        csv_file = tmp_path / "big.csv"
        csv_file.write_text(
            "ts,price\n" + "\n".join("1,1" for _ in range(40)), encoding="utf-8"
        )

        ingestor = AsyncDataIngestor(allowed_roots=[tmp_path], max_csv_bytes=32)

        with pytest.raises(ValueError, match="exceeds"):
            async for _ in ingestor.read_csv(str(csv_file)):
                pass

    @pytest.mark.asyncio
    async def test_fetch_market_snapshot_via_connector(self) -> None:
        """Snapshot retrieval should call into the configured connector."""

        ticks = [
            Ticker.create(
                symbol="BTCUSD",
                venue="COINBASE",
                price=30000.0,
                timestamp=datetime.fromtimestamp(1700000000, tz=timezone.utc),
                volume=5.0,
            )
        ]

        adapters: list[DummyAdapter] = []

        def factory() -> BaseMarketDataConnector:
            adapter = DummyAdapter(ticks)
            adapters.append(adapter)
            return BaseMarketDataConnector(adapter)

        ingestor = AsyncDataIngestor(market_connectors={"coinbase": factory})
        snapshot = await ingestor.fetch_market_snapshot("coinbase", symbol="BTCUSD")

        assert len(snapshot) == 1
        assert float(snapshot[0].price) == 30000.0
        assert adapters and adapters[0].closed is True

    @pytest.mark.asyncio
    async def test_fetch_market_snapshot_requires_connector(self) -> None:
        """Requesting a snapshot for an unknown source should fail fast."""

        ingestor = AsyncDataIngestor()

        with pytest.raises(ValueError, match="No market data connector"):
            await ingestor.fetch_market_snapshot("binance", symbol="BTCUSDT")


class TestMergeStreams:
    """Test stream merging functionality."""

    async def generate_ticks(
        self, symbol: str, count: int, delay_ms: int = 5
    ) -> AsyncIterator[Ticker]:
        """Helper to generate ticks."""
        for i in range(count):
            await asyncio.sleep(delay_ms / 1000.0)
            yield Ticker.create(
                symbol=symbol,
                venue="TEST",
                price=100.0 + i,
                timestamp=datetime.fromtimestamp(float(i), tz=timezone.utc),
                volume=1000,
            )

    @pytest.mark.asyncio
    async def test_merge_two_streams(self) -> None:
        """Test merging two async streams."""
        stream1 = self.generate_ticks("BTC", 3)
        stream2 = self.generate_ticks("ETH", 3)

        ticks = []
        async for tick in merge_streams(stream1, stream2):
            ticks.append(tick)

        assert len(ticks) == 6
        symbols = [tick.symbol for tick in ticks]
        assert "BTC" in symbols
        assert "ETH" in symbols

    @pytest.mark.asyncio
    async def test_merge_empty_stream(self) -> None:
        """Test merging with empty stream."""

        async def empty_stream():
            return
            yield  # Make it a generator

        stream1 = self.generate_ticks("BTC", 2)
        stream2 = empty_stream()

        ticks = []
        async for tick in merge_streams(stream1, stream2):
            ticks.append(tick)

        assert len(ticks) == 2
        assert all(tick.symbol == "BTC" for tick in ticks)

    @pytest.mark.asyncio
    async def test_merge_streams_handles_failures(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Failed streams should be logged and skipped while others continue."""

        async def flaky_stream():
            yield Ticker.create(
                symbol="FLAKY",
                venue="TEST",
                price=101.0,
                timestamp=datetime.fromtimestamp(0, tz=timezone.utc),
                volume=1_000,
            )
            raise ConnectionError("network down")

        stream_ok = self.generate_ticks("BTC", 3, delay_ms=1)

        caplog.set_level("WARNING")
        merged = merge_streams(stream_ok, flaky_stream())
        received: list[Ticker] = []

        async for tick in merged:
            received.append(tick)
            if len(received) >= 4:
                break

        prices = [str(tick.price) for tick in received]
        assert "101.0" in prices
        assert any(
            "Async stream terminated with error" in record.message
            for record in caplog.records
        )


class TestAsyncWebSocketStream:
    """Tests for the WebSocket helper."""

    @pytest.mark.asyncio
    async def test_stream_subscribes_and_decodes_messages(self) -> None:
        from core.data.async_ingestion import AsyncWebSocketStream

        class _StubWebSocket:
            def __init__(self, *messages: str) -> None:
                self._messages = deque(messages)
                self.sent: list[object] = []
                self.closed = False

            async def send(self, message: object) -> None:
                self.sent.append(message)

            async def recv(self) -> str | None:
                await asyncio.sleep(0)
                if not self._messages:
                    return None
                return self._messages.popleft()

            async def close(self) -> None:
                self.closed = True

        first = json.dumps(
            {
                "symbol": "BTCUSD",
                "venue": "BINANCE",
                "price": "100.5",
                "timestamp": 1_719_878_400,
                "volume": 1.25,
            }
        )
        second = json.dumps(
            {
                "symbol": "BTCUSD",
                "venue": "BINANCE",
                "price": "101.0",
                "timestamp": 1_719_878_460,
                "volume": 2.0,
            }
        )
        connection = _StubWebSocket(first, second)

        stream = AsyncWebSocketStream(
            "ws://example",
            "BTCUSD",
            connection_factory=lambda _: connection,
            subscription_message=lambda symbol: {"type": "subscribe", "symbol": symbol},
        )

        ticks: list[Ticker] = []
        async for tick in stream.subscribe():
            ticks.append(tick)

        assert len(ticks) == 2
        assert connection.closed is True
        assert connection.sent == ['{"type":"subscribe","symbol":"BTCUSD"}']
        assert ticks[0].symbol.replace("/", "") == "BTCUSD"
        assert float(ticks[0].price) == pytest.approx(100.5, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)
        assert float(ticks[1].price) == pytest.approx(101.0, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)

    @pytest.mark.asyncio
    async def test_stream_skips_malformed_payloads(self, caplog: pytest.LogCaptureFixture) -> None:
        from core.data.async_ingestion import AsyncWebSocketStream

        class _StubWebSocket:
            def __init__(self, *messages: str) -> None:
                self._messages = deque(messages)

            async def send(self, message: object) -> None:
                pass

            async def recv(self) -> str | None:
                await asyncio.sleep(0)
                if not self._messages:
                    return None
                return self._messages.popleft()

            async def close(self) -> None:
                return None

        good = json.dumps(
            {
                "symbol": "ETHUSD",
                "venue": "BINANCE",
                "price": "2500.0",
                "timestamp": 1_719_878_520,
            }
        )
        connection = _StubWebSocket("not-json", good)

        stream = AsyncWebSocketStream(
            "ws://example",
            "ETHUSD",
            connection_factory=lambda _: connection,
        )

        caplog.set_level("DEBUG")
        ticks = [tick async for tick in stream.subscribe()]

        assert len(ticks) == 1
        assert ticks[0].symbol.replace("/", "") == "ETHUSD"
        assert any("Discarding malformed WebSocket payload" in record.message for record in caplog.records)
