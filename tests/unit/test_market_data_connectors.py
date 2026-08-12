# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for schema-aware market data connectors."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, AsyncIterator, List

import pytest
from packaging.version import Version

from core.data.adapters.base import IngestionAdapter, RetryConfig
from core.data.connectors import (
    BinanceMarketDataConnector,
    CoinbaseMarketDataConnector,
    DeadLetterQueue,
    PolygonMarketDataConnector,
)
from core.data.models import InstrumentType, MarketMetadata, PriceTick


class DummyAdapter(IngestionAdapter):
    """Test double providing deterministic fetch/stream behaviour."""

    def __init__(
        self,
        *,
        fetch_result: List[Any] | None = None,
        stream_items: List[Any] | None = None,
        stream_error: Exception | None = None,
        retry: RetryConfig | None = None,
    ) -> None:
        super().__init__(retry=retry)
        self.fetch_result = fetch_result or []
        self.stream_items = stream_items or []
        self.stream_error = stream_error
        self.stream_calls = 0

    async def fetch(self, **kwargs: Any) -> List[Any]:  # pragma: no cover - exercised via connector
        return list(self.fetch_result)

    async def stream(
        self, **kwargs: Any
    ) -> AsyncIterator[Any]:  # pragma: no cover - exercised via connector
        self.stream_calls += 1
        for item in self.stream_items:
            yield item
        if self.stream_error is not None:
            raise self.stream_error

    async def aclose(self) -> None:  # pragma: no cover - trivial
        return None


class FlakyAdapter(DummyAdapter):
    def __init__(
        self,
        *,
        stream_items: List[Any] | None = None,
        retry: RetryConfig | None = None,
    ) -> None:
        super().__init__(
            stream_items=stream_items,
            stream_error=RuntimeError("boom"),
            retry=retry,
        )
        self._failures = 0

    async def stream(
        self, **kwargs: Any
    ) -> AsyncIterator[Any]:  # pragma: no cover - exercised in tests
        self.stream_calls += 1
        if self._failures < 1:
            self._failures += 1
            raise self.stream_error  # type: ignore[misc]
        for item in self.stream_items:
            yield item


def _make_tick(symbol: str = "BTCUSDT", venue: str = "BINANCE") -> PriceTick:
    return PriceTick(
        metadata=MarketMetadata(symbol=symbol, venue=venue, instrument_type=InstrumentType.SPOT),
        timestamp=datetime.now(timezone.utc),
        price=Decimal("30123.45"),
        volume=Decimal("12.5"),
    )


@pytest.mark.asyncio
async def test_binance_connector_fetch_snapshot_produces_tick_events() -> None:
    tick = _make_tick()
    adapter = DummyAdapter(fetch_result=[tick])
    connector = BinanceMarketDataConnector(adapter=adapter)

    events = await connector.fetch_snapshot(symbol="BTC/USDT", timeframe="1m")

    assert len(events) == 1
    event = events[0]
    assert event.symbol == tick.symbol
    assert Version(event.schema_version) >= Version("1.0.0")
    assert event.bid_price == pytest.approx(float(tick.price))
    assert event.volume == int(tick.volume)


@pytest.mark.asyncio
async def test_streaming_errors_are_routed_to_dead_letter_queue() -> None:
    valid_tick = _make_tick()
    faulty_payload = object()
    adapter = DummyAdapter(stream_items=[valid_tick, faulty_payload])
    connector = CoinbaseMarketDataConnector(adapter=adapter)

    received: list = []
    async for event in connector.stream_ticks(symbol="BTC-USD"):
        received.append(event)

    assert len(received) == 1
    dlq_items = connector.dead_letter_queue.peek()
    assert len(dlq_items) == 1
    assert dlq_items[0].context == "stream"
    assert "object" in dlq_items[0].error


@pytest.mark.asyncio
async def test_streaming_retry_applies_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    computed: list[float] = []
    recorded: list[float] = []

    def _fake_backoff(self, attempt_number: int) -> float:  # type: ignore[override]
        delay = float(2**attempt_number)
        computed.append(delay)
        return delay

    async def _fake_sleep(delay: float) -> None:
        recorded.append(delay)

    monkeypatch.setattr(
        "core.data.adapters.base.RetryConfig.compute_backoff",
        _fake_backoff,
        raising=False,
    )
    monkeypatch.setattr("core.data.adapters.base.asyncio.sleep", _fake_sleep)

    tick = _make_tick()
    adapter = FlakyAdapter(
        stream_items=[tick],
        retry=RetryConfig(multiplier=1.0, max_backoff=60.0, jitter=0.0),
    )
    connector = BinanceMarketDataConnector(adapter=adapter)

    events = []
    async for event in connector.stream_ticks(symbol="BTCUSDT"):
        events.append(event)
        break

    assert events and events[0].symbol == tick.symbol
    assert adapter.stream_calls >= 2
    assert computed == [2.0]
    assert recorded == [2.0]


def test_dead_letter_queue_eviction_and_serialisation() -> None:
    queue = DeadLetterQueue(max_items=2)
    queue.push({"foo": "bar"}, ValueError("failure"), context="test")
    queue.push(_make_tick().model_dump(), RuntimeError("boom"), context="test")
    queue.push("payload", "error", context="test")

    items = queue.peek()
    assert len(items) == 2
    assert items[-1].payload == "payload"
    assert all(item.context == "test" for item in items)


@pytest.mark.asyncio
async def test_polygon_connector_fetch_aggregates_uses_adapter() -> None:
    tick = _make_tick(symbol="AAPL", venue="POLYGON")
    adapter = DummyAdapter(fetch_result=[tick])
    connector = PolygonMarketDataConnector(api_key="dummy", adapter=adapter)

    events = await connector.fetch_aggregates(symbol="AAPL", start="2024-01-01", end="2024-01-02")

    assert len(events) == 1
    event = events[0]
    assert event.symbol == tick.symbol
    assert event.bid_price == pytest.approx(float(tick.price))
    assert connector.dead_letter_queue.peek() == []
