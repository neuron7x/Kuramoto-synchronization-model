# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import json
from datetime import datetime, timezone

import pytest

from core.data.models import InstrumentType, PriceTick
from src.data.event_bus import BrokerMessage
from src.data.ingestion_service import DataIngestionCacheService
from src.data.kafka_ingestion import KafkaIngestionConfig
from src.data.pipeline import (
    CacheRoute,
    CacheWriterTickHandler,
    StaticTickRoutingStrategy,
    StreamingIngestionPipeline,
)


class _RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def publish_batch(self, event) -> None:
        payload = json.loads(event.to_payload().decode("utf-8"))
        self.events.append(payload)


class _RecordingBroker:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0
        self.published: list[BrokerMessage] = []

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1

    async def publish(self, message: BrokerMessage) -> None:
        self.published.append(message)


class _StubKafkaService:
    def __init__(self, tick_handler) -> None:
        self.tick_handler = tick_handler
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


@pytest.mark.asyncio
async def test_cache_writer_emits_event_metadata() -> None:
    publisher = _RecordingPublisher()
    handler = CacheWriterTickHandler(
        cache_service=DataIngestionCacheService(),
        routing_strategy=StaticTickRoutingStrategy(
            CacheRoute(layer="raw", timeframe="1min")
        ),
        event_publisher=publisher,
    )
    tick = PriceTick.create(
        symbol="ETHUSD",
        venue="BINANCE",
        price=1800,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        instrument_type=InstrumentType.SPOT,
    )
    await handler([tick])
    assert publisher.events
    payload = publisher.events[0]
    assert payload["symbol"] == "ETH/USD"
    assert payload["event_type"] == "data.tick_batch.persisted"
    assert payload["batch_size"] == 1


@pytest.mark.asyncio
async def test_pipeline_integrates_message_broker(tmp_path) -> None:
    broker = _RecordingBroker()
    config = KafkaIngestionConfig(
        topic="test",
        bootstrap_servers="localhost:9092",
        group_id="grp",
    )

    def factory(cfg, *, tick_handler, lag_handler):
        return _StubKafkaService(tick_handler)

    pipeline = StreamingIngestionPipeline(
        kafka_config=config,
        message_broker=broker,
        kafka_service_factory=factory,
    )

    await pipeline.start()
    tick = PriceTick.create(
        symbol="ETHUSD",
        venue="BINANCE",
        price=1000,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        instrument_type=InstrumentType.SPOT,
    )
    await pipeline.tick_handler([tick])
    await pipeline.stop()

    assert broker.started == 1
    assert broker.stopped == 1
    assert broker.published
    message = broker.published[0]
    payload = json.loads(message.payload.decode("utf-8"))
    assert payload["event_type"] == "data.tick_batch.persisted"
    assert message.topic == "geosync.data.tick_batch.persisted"
