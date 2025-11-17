"""Integration tests exercising real dependency interactions for TradePulse."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError as SAOperationalError
from sqlalchemy.orm import Session

from core.data.models import InstrumentType
from execution.risk import KillSwitch, PostgresKillSwitchStateStore
from libs.db import RetryPolicy
from libs.db.models import KillSwitchState
from libs.db.repository import KillSwitchStateRepository
from libs.db.session import SessionManager
from src.audit.audit_logger import AuditLogger, SiemAuditSink
from src.data.ingestion_service import DataIngestionCacheService
from src.data.kafka_ingestion import (
    KafkaIngestionConfig,
    KafkaIngestionService,
    LagRecord,
    LagReport,
)
from src.data.pipeline import (
    CacheRoute,
    StaticTickRoutingStrategy,
    StreamingIngestionPipeline,
)


class _FlakyKillSwitchStateRepository(KillSwitchStateRepository):
    """Repository that fails once to exercise retry/backoff logic."""

    def __init__(
        self, session_manager: SessionManager, *, retry_policy: RetryPolicy
    ) -> None:
        super().__init__(
            session_manager,
            retry_policy=retry_policy,
            logger=logging.getLogger("test.flaky_repo"),
        )
        self.attempts = 0

    def upsert(self, *, engaged: bool, reason: str):  # type: ignore[override]
        self.attempts += 1
        if self.attempts == 1:
            raise SAOperationalError(
                "INSERT kill_switch_state",
                {},
                RuntimeError("transient failure"),
            )
        return super().upsert(engaged=engaged, reason=reason)

    def load(self):  # type: ignore[override]
        return self._execute(_load_state_tuple, read_only=True)


class _TupleKillSwitchStateRepository(KillSwitchStateRepository):
    """Repository that returns tuples to avoid detached ORM state."""

    def load(self):  # type: ignore[override]
        return self._execute(_load_state_tuple, read_only=True)


def _load_state_tuple(session: Session):
    stmt = select(
        KillSwitchState.engaged,
        KillSwitchState.reason,
        KillSwitchState.updated_at,
    ).where(KillSwitchState.id == 1)
    result = session.execute(stmt).first()
    return result


def _sqlite_session_manager(db_path: Path) -> SessionManager:
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
    return SessionManager(engine, (), expire_on_commit=False)


def test_postgres_kill_switch_store_handles_transient_failures(tmp_path: Path) -> None:
    db_path = tmp_path / "kill_switch.sqlite"
    session_manager = _sqlite_session_manager(db_path)
    base_repo = KillSwitchStateRepository(session_manager)
    base_repo.ensure_schema()
    base_repo.upsert(engaged=False, reason="seed state")

    retry_policy = RetryPolicy(
        attempts=3, initial_backoff=0.01, max_backoff=0.05, max_jitter=0.01
    )
    flaky_repo = _FlakyKillSwitchStateRepository(
        session_manager, retry_policy=retry_policy
    )
    store = PostgresKillSwitchStateStore(
        "postgresql://integration",
        session_manager=session_manager,
        repository=flaky_repo,
        retry_policy=retry_policy,
        ensure_schema=False,
    )
    kill_switch = KillSwitch(store)

    assert kill_switch.is_triggered() is False

    kill_switch.trigger("transient failure recovered")

    assert flaky_repo.attempts >= 2

    with session_manager.session(read_only=True) as session:
        row = session.execute(select(KillSwitchState)).scalar_one()
        assert row.engaged is True
        assert row.reason == "transient failure recovered"

    store.close()

    session_manager = _sqlite_session_manager(db_path)
    restored_repo = _TupleKillSwitchStateRepository(session_manager)
    restored_store = PostgresKillSwitchStateStore(
        "postgresql://integration",
        session_manager=session_manager,
        repository=restored_repo,
        retry_policy=retry_policy,
        ensure_schema=False,
    )
    restored_switch = KillSwitch(restored_store)
    assert restored_switch.is_triggered() is True
    assert restored_switch.reason == "transient failure recovered"
    restored_store.close()


@dataclass(frozen=True)
class _TopicPartition:
    topic: str
    partition: int

    def __hash__(self) -> int:
        return hash((self.topic, self.partition))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _TopicPartition):
            return NotImplemented
        return self.topic == other.topic and self.partition == other.partition


@dataclass
class _FakeMessage:
    offset: int
    value: bytes
    headers: list[tuple[str, bytes]]
    key: bytes | None = None


class _FakeKafkaProducer:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0
        self.begin_calls = 0
        self.commit_calls = 0
        self.abort_calls = 0
        self.offset_commits: list[tuple[dict[_TopicPartition, int], str]] = []

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1

    async def begin_transaction(self) -> None:
        self.begin_calls += 1

    async def send_offsets_to_transaction(
        self, offsets: Mapping[_TopicPartition, int], group_id: str
    ) -> None:
        self.offset_commits.append((dict(offsets), group_id))

    async def commit_transaction(self) -> None:
        self.commit_calls += 1

    async def abort_transaction(self) -> None:
        self.abort_calls += 1


class _FakeKafkaConsumer:
    def __init__(
        self,
        batches: deque[dict[_TopicPartition, list[_FakeMessage]]],
        *,
        end_offsets: dict[_TopicPartition, int],
    ) -> None:
        self._batches = batches
        self._assignment = {tp for batch in batches for tp in batch}
        self._end_offsets = end_offsets
        self.seek_calls: list[tuple[_TopicPartition, int]] = []
        self.started = 0
        self.stopped = 0
        self.drained = asyncio.Event()

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1

    async def getmany(
        self, timeout_ms: int, max_records: int
    ) -> dict[_TopicPartition, list[_FakeMessage]]:
        if not self._batches:
            self.drained.set()
            await asyncio.sleep(timeout_ms / 1000)
            return {}
        batch = self._batches.popleft()
        if not self._batches:
            self.drained.set()
        return batch

    def assignment(self) -> set[_TopicPartition]:
        return set(self._assignment)

    async def end_offsets(
        self, partitions: list[_TopicPartition]
    ) -> dict[_TopicPartition, int]:
        return {tp: self._end_offsets.get(tp, 0) for tp in partitions}

    async def seek(self, tp: _TopicPartition, offset: int) -> None:
        self.seek_calls.append((tp, offset))


@pytest.mark.asyncio
async def test_streaming_pipeline_processes_kafka_batches_and_updates_cache(
    tmp_path: Path,
) -> None:
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

    def _message(offset: int, event_id: str, price: float) -> _FakeMessage:
        occurred_at = base_time + timedelta(seconds=offset)
        payload = {
            "symbol": "BTCUSD",
            "venue": "BINANCE",
            "price": price,
            "timestamp": occurred_at.timestamp(),
        }
        headers = [
            ("event_id", event_id.encode("utf-8")),
            ("symbol", b"BTCUSD"),
            ("venue", b"BINANCE"),
            ("occurred_at", occurred_at.isoformat().encode("utf-8")),
        ]
        return _FakeMessage(
            offset=offset, value=json.dumps(payload).encode("utf-8"), headers=headers
        )

    topic_partition = _TopicPartition(topic="tradepulse.market.ticks", partition=0)
    batches: deque[dict[_TopicPartition, list[_FakeMessage]]] = deque(
        [
            {
                topic_partition: [
                    _message(0, "evt-0", 100.0),
                    _message(1, "evt-1", 101.0),
                ]
            },
            {
                topic_partition: [
                    _message(2, "evt-1", 999.0),
                    _message(3, "evt-3", 102.0),
                ]
            },
        ]
    )
    consumer = _FakeKafkaConsumer(batches, end_offsets={topic_partition: 6})
    producer = _FakeKafkaProducer()

    lag_reports: list[LagReport] = []

    async def lag_handler(report: LagReport) -> None:
        lag_reports.append(report)

    cache_service = DataIngestionCacheService()
    config = KafkaIngestionConfig(
        topic="tradepulse.market.ticks",
        bootstrap_servers="kafka:9092",
        group_id="tradepulse-test",
        lag_report_interval_seconds=0.05,
        lag_detection_threshold=0,
        reconcile_seek_on_gap=False,
    )

    def factory(
        cfg: KafkaIngestionConfig,
        *,
        tick_handler,
        lag_handler,
    ) -> KafkaIngestionService:
        return KafkaIngestionService(
            cfg,
            tick_handler=tick_handler,
            lag_handler=lag_handler,
            consumer=consumer,
            producer=producer,
        )

    pipeline = StreamingIngestionPipeline(
        kafka_config=config,
        cache_service=cache_service,
        routing_strategy=StaticTickRoutingStrategy(
            CacheRoute(layer="raw", timeframe="1min")
        ),
        lag_handler=lag_handler,
        kafka_service_factory=factory,
    )

    await pipeline.start()
    await asyncio.wait_for(consumer.drained.wait(), timeout=1.0)
    await pipeline.kafka_service._emit_lag_report(
        [
            LagRecord(
                topic=config.topic,
                partition=0,
                expected_offset=4,
                observed_offset=6,
                lag=2,
            )
        ]
    )
    await pipeline.stop()

    assert producer.started == 1
    assert producer.commit_calls >= 1
    assert producer.abort_calls == 0

    metadata = cache_service.metadata_for(
        layer="raw",
        symbol="BTCUSD",
        venue="BINANCE",
        timeframe="1min",
    )
    assert metadata is not None
    assert metadata.rows == 1

    frame = cache_service.get_cached_frame(
        layer="raw",
        symbol="BTCUSD",
        venue="BINANCE",
        timeframe="1min",
    )
    assert frame.shape[0] == 1
    assert pytest.approx(frame["price"].iloc[0]) == 102.0

    hot_snapshot = pipeline.kafka_service.hot_cache.snapshot(
        "BTCUSD", "BINANCE", InstrumentType.SPOT
    )
    assert hot_snapshot is None or not hot_snapshot.ticks

    assert lag_reports
    assert pipeline.kafka_service._idempotency.was_processed("evt-1") is True
    assert producer.offset_commits
    last_offsets, group = producer.offset_commits[-1]
    assert group == "tradepulse-test"
    assert last_offsets.get(topic_partition) == 4


def _wait_for(predicate, *, timeout: float = 5.0, interval: float = 0.05) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("Condition not met within timeout")


def test_siem_audit_sink_retries_and_drains_spool(tmp_path: Path) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"status": "retry"})
        return httpx.Response(200, json={"status": "ok"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    spool_dir = tmp_path / "spool"
    sink = SiemAuditSink(
        "https://audit.tradepulse.test",
        spool_dir,
        http_client=client,
        max_retries=5,
        base_backoff_seconds=0.0,
        max_backoff_seconds=0.01,
        sleep=lambda _: None,
    )
    logger = AuditLogger(secret="integration-secret", sink=sink)
    record = logger.log_event(
        event_type="admin.login",
        actor="ops",
        ip_address="203.0.113.10",
        details={"scope": "integration"},
    )
    assert record.signature

    def _spool_empty() -> bool:
        return not list(spool_dir.glob("*.json")) and not list(
            spool_dir.glob("*.json.inflight")
        )

    _wait_for(lambda: attempts >= 3 and _spool_empty(), timeout=2.0)

    sink.close()
    client.close()

    assert attempts == 3
    assert _spool_empty()
    dead_letter = spool_dir / "dead-letter"
    assert not any(dead_letter.iterdir())
