# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Producer-lifecycle integrity for the Kafka event bus.

KafkaEventBus had an orphaned consumer task (fixed in #1448). These tests close
the remaining producer-lifecycle gaps so no asynchronous handle survives a stop:
``stop()`` drops the producer, which makes it idempotent and makes a publish after
stop fail closed rather than driving a stopped producer. Consumer-side lifecycle
(subscribe tracking, dup-no-orphan, poison→DLQ, idempotency) is bound to its
existing tests by ``artifacts/messaging/event_bus_lifecycle_matrix.json``.
"""

from __future__ import annotations

import asyncio

import pytest

from core.messaging.event_bus import (
    EventBusBackend,
    EventBusConfig,
    EventEnvelope,
    EventTopic,
    KafkaEventBus,
)


class _FakeProducer:
    def __init__(self) -> None:
        self.stopped = 0
        self.sent = 0

    async def stop(self) -> None:
        self.stopped += 1

    async def send_and_wait(self, *args: object, **kwargs: object) -> None:
        self.sent += 1


def _bus() -> KafkaEventBus:
    return KafkaEventBus(
        EventBusConfig(backend=EventBusBackend.KAFKA, bootstrap_servers="localhost:9092")
    )


@pytest.mark.asyncio
async def test_stop_cancels_every_consumer_task_and_clears_map() -> None:
    bus = _bus()

    async def _forever() -> None:
        await asyncio.sleep(3600)

    task_a = asyncio.create_task(_forever())
    task_b = asyncio.create_task(_forever())
    bus._consumer_tasks = {"a": [task_a], "b": [task_b]}
    bus._producer = _FakeProducer()

    await bus.stop()

    assert task_a.cancelled() and task_b.cancelled()
    assert bus._consumer_tasks == {}


@pytest.mark.asyncio
async def test_stop_is_idempotent() -> None:
    bus = _bus()
    producer = _FakeProducer()
    bus._producer = producer

    await bus.stop()
    await bus.stop()  # second stop must not raise or re-stop a dropped producer

    assert bus._producer is None
    assert producer.stopped == 1  # stopped exactly once


@pytest.mark.asyncio
async def test_publish_after_stop_fails_closed() -> None:
    bus = _bus()
    bus._producer = _FakeProducer()
    await bus.stop()

    envelope = EventEnvelope(
        event_type="market.tick",
        partition_key="BTC-USD",
        event_id="e1",
        payload=b"{}",
        content_type="application/json",
        schema_version="1",
    )
    with pytest.raises(RuntimeError):
        await bus.publish(EventTopic.MARKET_TICKS, envelope)
