# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from typing import Any, Dict

import pytest

from core.messaging.event_bus import (
    EventBusBackend,
    EventBusConfig,
    EventEnvelope,
    EventTopic,
    KafkaEventBus,
)
from core.messaging.idempotency import InMemoryEventIdempotencyStore


class DummyProducer:
    def __init__(self) -> None:
        self.calls: list[Dict[str, Any]] = []

    async def send_and_wait(
        self, topic: str, value: bytes, *, key: bytes, headers: list[tuple[str, bytes]]
    ) -> None:
        self.calls.append({"topic": topic, "value": value, "key": key, "headers": headers})


@pytest.mark.asyncio
async def test_kafka_publish_uses_symbol_partition_key() -> None:
    config = EventBusConfig(backend=EventBusBackend.KAFKA, bootstrap_servers="kafka:9092")
    bus = KafkaEventBus(config)
    producer = DummyProducer()
    bus._producer = producer  # type: ignore[attr-defined]

    envelope = EventEnvelope(
        event_type="ticks",
        partition_key="AAPL",
        event_id="evt-1",
        payload=b"payload",
        content_type="avro/binary",
        schema_version="1.0.0",
    )

    await bus.publish(EventTopic.MARKET_TICKS, envelope)
    assert producer.calls[0]["topic"] == EventTopic.MARKET_TICKS.metadata.name
    assert producer.calls[0]["key"] == b"AAPL"


def test_idempotent_store_marks_processed() -> None:
    store = InMemoryEventIdempotencyStore(ttl_seconds=1)
    assert not store.was_processed("abc")
    store.mark_processed("abc")
    assert store.was_processed("abc")
    # Force expiry by manipulating the underlying timestamp
    record = store._records["abc"]  # type: ignore[attr-defined]
    record.timestamp -= 2
    # Purge lazily on next check
    assert not store.was_processed("abc")
