from __future__ import annotations

import asyncio
import json
import ssl
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pytest

from core.data.models import InstrumentType
from src.data.kafka_ingestion import (
    KafkaIngestionConfig,
    KafkaIngestionService,
    LagReport,
)


@dataclass(frozen=True)
class TopicPartition:
    topic: str
    partition: int


@dataclass
class StubMessage:
    topic: str
    partition: int
    offset: int
    key: bytes | None
    value: bytes
    headers: list[tuple[str, bytes]]


class StubConsumer:
    def __init__(self, messages: dict[TopicPartition, list[StubMessage]]) -> None:
        self._all_messages = {tp: list(msgs) for tp, msgs in messages.items()}
        self._buffers = {tp: deque(msgs) for tp, msgs in messages.items()}
        self._committed: dict[TopicPartition, int] = {tp: 0 for tp in messages}
        self._positions: dict[TopicPartition, int] = {tp: 0 for tp in messages}
        self._started = False
        self.seek_calls: list[tuple[TopicPartition, int]] = []

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False

    async def getmany(
        self, *, timeout_ms: int, max_records: int
    ) -> dict[Any, list[StubMessage]]:
        if not self._started:
            raise RuntimeError("Consumer must be started before polling")
        results: dict[Any, list[StubMessage]] = {}
        remaining = max_records
        for tp, queue in self._buffers.items():
            if not queue or remaining <= 0:
                continue
            batch: list[StubMessage] = []
            while queue and remaining > 0:
                msg = queue.popleft()
                batch.append(msg)
                self._positions[tp] = msg.offset + 1
                remaining -= 1
            if batch:
                results[tp] = batch
        await asyncio.sleep(0)
        return results

    def assignment(self) -> set[TopicPartition]:
        return set(self._buffers.keys())

    async def end_offsets(
        self, partitions: Iterable[TopicPartition]
    ) -> dict[TopicPartition, int]:
        end_offsets: dict[TopicPartition, int] = {}
        for tp in partitions:
            messages = self._all_messages.get(tp, [])
            if not messages:
                end_offsets[tp] = 0
            else:
                end_offsets[tp] = max(msg.offset for msg in messages) + 1
        await asyncio.sleep(0)
        return end_offsets

    async def seek(self, tp: TopicPartition, offset: int) -> None:
        self.seek_calls.append((tp, offset))
        all_msgs = sorted(self._all_messages.get(tp, []), key=lambda msg: msg.offset)
        self._buffers[tp] = deque([msg for msg in all_msgs if msg.offset >= offset])
        self._positions[tp] = offset
        await asyncio.sleep(0)

    async def committed(self, tp: TopicPartition) -> int:
        await asyncio.sleep(0)
        return self._committed.get(tp, 0)

    async def position(self, tp: TopicPartition) -> int:
        await asyncio.sleep(0)
        return self._positions.get(tp, 0)

    def commit(self, offsets: dict[Any, int]) -> None:
        for tp, offset in offsets.items():
            self._committed[tp] = offset


class StubProducer:
    def __init__(self, consumer: StubConsumer) -> None:
        self._consumer = consumer
        self._started = False
        self.transactions_started = 0
        self.commits = 0
        self.aborts = 0
        self._pending_offsets: dict[Any, int] | None = None

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False

    async def begin_transaction(self) -> None:
        self.transactions_started += 1

    async def send_offsets_to_transaction(
        self, offsets: dict[Any, int], group_id: str
    ) -> None:
        self._pending_offsets = dict(offsets)

    async def commit_transaction(self) -> None:
        if self._pending_offsets is not None:
            self._consumer.commit(self._pending_offsets)
        self.commits += 1
        self._pending_offsets = None

    async def abort_transaction(self) -> None:
        self.aborts += 1
        self._pending_offsets = None


def _build_message(
    tp: TopicPartition, offset: int, *, event_id: str | None = None
) -> StubMessage:
    payload = {
        "symbol": "AAPL",
        "venue": "NASDAQ",
        "price": 100 + offset,
        "timestamp": 1_700_000_000 + offset,
        "volume": 1,
        "instrument_type": InstrumentType.SPOT.value,
        "trade_id": f"trade-{offset}",
    }
    headers = [("event_id", (event_id or f"evt-{offset}").encode("utf-8"))]
    value = json.dumps(payload).encode("utf-8")
    return StubMessage(
        topic=tp.topic,
        partition=tp.partition,
        offset=offset,
        key=payload["symbol"].encode("utf-8"),
        value=value,
        headers=headers,
    )


@pytest.mark.asyncio
async def test_ingestion_deduplicates_events() -> None:
    tp = TopicPartition("tradepulse.market.ticks", 0)
    messages = [
        _build_message(tp, offset=0, event_id="evt-shared"),
        _build_message(tp, offset=1, event_id="evt-shared"),
    ]
    consumer = StubConsumer({tp: messages})
    producer = StubProducer(consumer)
    config = KafkaIngestionConfig(
        topic=tp.topic,
        bootstrap_servers="kafka:9092",
        group_id="tradepulse-test",
        lag_report_interval_seconds=10.0,
    )
    processed_prices: list[float] = []

    async def handler(ticks):
        processed_prices.extend(float(tick.price) for tick in ticks)

    service = KafkaIngestionService(
        config,
        tick_handler=handler,
        consumer=consumer,
        producer=producer,
    )

    await service.start()
    await asyncio.sleep(0.05)
    await service.stop()

    assert processed_prices == [100.0]
    assert producer.transactions_started >= 1
    assert producer.commits >= 1
    assert producer.aborts == 0


@pytest.mark.asyncio
async def test_hot_symbol_cache_tracks_recent_ticks() -> None:
    tp = TopicPartition("tradepulse.market.ticks", 0)
    messages = [_build_message(tp, offset=i) for i in range(3)]
    consumer = StubConsumer({tp: messages})
    producer = StubProducer(consumer)
    config = KafkaIngestionConfig(
        topic=tp.topic,
        bootstrap_servers="kafka:9092",
        group_id="tradepulse-test",
        hot_cache_flush_size=10,
        lag_report_interval_seconds=10.0,
    )
    service = KafkaIngestionService(config, consumer=consumer, producer=producer)

    await service.start()
    await asyncio.sleep(0.05)
    await service.stop()

    snapshot = service.hot_cache.snapshot("AAPL", "NASDAQ", InstrumentType.SPOT)
    assert snapshot is not None
    assert len(snapshot.ticks) == 3
    assert all(tick.symbol == "AAPL" for tick in snapshot.ticks)


@pytest.mark.asyncio
async def test_gap_detection_triggers_seek_and_lag_report() -> None:
    tp = TopicPartition("tradepulse.market.ticks", 0)
    messages = [
        _build_message(tp, offset=0),
        _build_message(tp, offset=2),
        _build_message(tp, offset=1),
    ]
    consumer = StubConsumer({tp: messages})
    producer = StubProducer(consumer)
    reports: list[LagReport] = []

    async def lag_handler(report: LagReport) -> None:
        reports.append(report)

    processed: list[float] = []

    async def handler(ticks):
        processed.extend(float(tick.price) for tick in ticks)

    config = KafkaIngestionConfig(
        topic=tp.topic,
        bootstrap_servers="kafka:9092",
        group_id="tradepulse-test",
        lag_detection_threshold=1,
        lag_report_interval_seconds=10.0,
        reconcile_seek_on_gap=True,
    )
    service = KafkaIngestionService(
        config,
        tick_handler=handler,
        lag_handler=lag_handler,
        consumer=consumer,
        producer=producer,
    )

    await service.start()
    await asyncio.sleep(0.1)
    await service.stop()

    assert (
        consumer.seek_calls
    ), "Expected the service to reconcile partition gaps via seek"
    gap_offsets = {offset for _, offset in consumer.seek_calls}
    assert 1 in gap_offsets
    assert producer.aborts >= 1
    assert any(
        record.reason == "gap" for report in reports for record in report.records
    )
    assert sorted(processed) == [100.0, 101.0, 102.0]


def test_build_security_kwargs_requires_existing_cafile(tmp_path: Path) -> None:
    missing_cafile = tmp_path / "missing.pem"
    config = KafkaIngestionConfig(
        topic="tradepulse.market.ticks",
        bootstrap_servers="kafka:9092",
        group_id="tradepulse-test",
        ssl_cafile=str(missing_cafile),
    )
    service = KafkaIngestionService(config)

    with pytest.raises(ValueError, match="ssl_cafile must point to an existing file"):
        service._build_security_kwargs()


def test_build_security_kwargs_validates_cert_and_key_files(tmp_path: Path) -> None:
    default_ca = (
        ssl.get_default_verify_paths().openssl_cafile
        or ssl.get_default_verify_paths().cafile
    )
    if default_ca is None or not Path(default_ca).is_file():
        pytest.skip("System CA bundle not available for SSL validation test")
    cafile = Path(default_ca)
    missing_cert = tmp_path / "cert.pem"
    keyfile = tmp_path / "key.pem"
    keyfile.write_text("key")
    config = KafkaIngestionConfig(
        topic="tradepulse.market.ticks",
        bootstrap_servers="kafka:9092",
        group_id="tradepulse-test",
        ssl_cafile=str(cafile),
        ssl_certfile=str(missing_cert),
        ssl_keyfile=str(keyfile),
    )
    service = KafkaIngestionService(config)

    with pytest.raises(ValueError, match="ssl_certfile must point to an existing file"):
        service._build_security_kwargs()
