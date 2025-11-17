from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from core.data.adapters.polygon import PolygonIngestionAdapter
from core.data.models import InstrumentType, PriceTick
from core.features.realtime_store import (
    FeatureDescriptor,
    FeatureLineage,
    RealTimeFeatureStore,
)
from src.data.kafka_ingestion import KafkaIngestionConfig
from src.data.pipeline import StreamingIngestionPipeline


class _FakeBroker:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0
        self.messages: list[Any] = []

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1

    async def publish(self, message: Any) -> None:
        self.messages.append(message)


class _CapturingKafkaService:
    def __init__(
        self, config: KafkaIngestionConfig, *, tick_handler, lag_handler=None
    ) -> None:
        self.config = config
        self.tick_handler = tick_handler
        self.lag_handler = lag_handler
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class _FakeRedisPipeline:
    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._operations: list[tuple[str, tuple[Any, ...]]] = []

    async def __aenter__(self) -> "_FakeRedisPipeline":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    def xadd(
        self,
        stream_key: str,
        payload: dict[str, str],
        *,
        maxlen: int,
        approximate: bool,
    ) -> "_FakeRedisPipeline":
        self._operations.append(("xadd", (stream_key, payload)))
        return self

    def set(self, key: str, value: str, *, px: int) -> "_FakeRedisPipeline":
        self._operations.append(("set", (key, value, px)))
        return self

    async def execute(self) -> list[Any]:
        results: list[Any] = []
        for op, args in self._operations:
            if op == "xadd":
                stream_key, payload = args
                results.append(self._redis._add_stream_entry(stream_key, payload))
            elif op == "set":
                key, value, px = args
                self._redis._set_value(key, value, px)
                results.append(True)
        self._operations.clear()
        return results


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.streams: dict[str, list[tuple[str, dict[bytes, bytes]]]] = {}

    def pipeline(self, *, transaction: bool = False) -> _FakeRedisPipeline:
        return _FakeRedisPipeline(self)

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def xread(
        self, *, streams: dict[str, str], count: int, block: int
    ) -> list[tuple[str, list[tuple[str, dict[bytes, bytes]]]]]:
        response: list[tuple[str, list[tuple[str, dict[bytes, bytes]]]]] = []
        for stream_key, last_id in streams.items():
            entries = self.streams.get(stream_key, [])
            selected: list[tuple[str, dict[bytes, bytes]]] = []
            for entry_id, payload in entries:
                if last_id != "$" and entry_id <= last_id:
                    continue
                selected.append((entry_id, payload))
            if selected:
                response.append((stream_key, selected[:count]))
        return response

    def _add_stream_entry(self, stream_key: str, payload: dict[str, str]) -> str:
        entries = self.streams.setdefault(stream_key, [])
        entry_id = f"{len(entries) + 1}-0"
        encoded: dict[bytes, bytes] = {}
        for key, value in payload.items():
            key_bytes = key.encode("utf-8") if isinstance(key, str) else key
            if isinstance(value, str):
                value_bytes = value.encode("utf-8")
            elif isinstance(value, bytes):
                value_bytes = value
            else:
                value_bytes = json.dumps(value).encode("utf-8")
            encoded[key_bytes] = value_bytes
        entries.append((entry_id, encoded))
        return entry_id

    def _set_value(self, key: str, value: str, ttl: int) -> None:
        self.store[key] = value


@dataclass(slots=True)
class _FeatureValueRecord:
    feature_name: str
    feature_version: str
    entity_id: str
    event_ts: datetime
    value: dict[str, Any]
    lineage: dict[str, Any] | None


class _FakeDatabase:
    def __init__(self) -> None:
        self.registry: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.feature_values: list[_FeatureValueRecord] = []


class _FakeConnection:
    def __init__(self, db: _FakeDatabase) -> None:
        self._db = db

    async def execute(self, query: str, *args: Any) -> str:
        normalized = " ".join(query.strip().split()).lower()
        if normalized.startswith("create table"):
            return "CREATE TABLE"
        if "create_hypertable" in normalized:
            return "SELECT 1"
        if normalized.startswith("insert into feature_registry"):
            name, version, entity, ttl_ms, schema_json, description = args
            schema = json.loads(schema_json) if schema_json else None
            self._db.registry[(name, version, entity)] = {
                "ttl_ms": ttl_ms,
                "schema": schema,
                "description": description,
            }
            return "INSERT 0 1"
        if normalized.startswith("insert into feature_values"):
            name, version, entity_id, event_ts, value_json, lineage_json = args
            value = json.loads(value_json)
            lineage = json.loads(lineage_json) if lineage_json else None
            existing = next(
                (
                    record
                    for record in self._db.feature_values
                    if record.feature_name == name
                    and record.feature_version == version
                    and record.entity_id == entity_id
                    and record.event_ts == event_ts
                ),
                None,
            )
            if existing is not None:
                return "INSERT 0 0"
            self._db.feature_values.append(
                _FeatureValueRecord(
                    feature_name=name,
                    feature_version=version,
                    entity_id=entity_id,
                    event_ts=event_ts,
                    value=value,
                    lineage=lineage,
                )
            )
            return "INSERT 0 1"
        if normalized.startswith("delete from feature_values"):
            name, version, entity_id, event_ts = args
            before = len(self._db.feature_values)
            self._db.feature_values = [
                record
                for record in self._db.feature_values
                if not (
                    record.feature_name == name
                    and record.feature_version == version
                    and record.entity_id == entity_id
                    and record.event_ts == event_ts
                )
            ]
            deleted = before - len(self._db.feature_values)
            return f"DELETE 0 {deleted}"
        return "OK"

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        normalized = " ".join(query.strip().split()).lower()
        if (
            "from feature_values" in normalized
            and "order by event_ts desc" in normalized
        ):
            name, version, entity_id = args[:3]
            cutoff: datetime | None = None
            if "event_ts <= $4" in normalized:
                cutoff = args[3]
            candidates = [
                record
                for record in self._db.feature_values
                if record.feature_name == name
                and record.feature_version == version
                and record.entity_id == entity_id
            ]
            if cutoff is not None:
                candidates = [
                    record for record in candidates if record.event_ts <= cutoff
                ]
            if not candidates:
                return None
            latest = max(candidates, key=lambda record: record.event_ts)
            return {
                "value": latest.value,
                "event_ts": latest.event_ts,
                "lineage": latest.lineage,
            }
        return None

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        normalized = " ".join(query.strip().split()).lower()
        if "from feature_values" in normalized and "any($3::text[])" in normalized:
            name, version, entities, cutoff = args
            results: list[dict[str, Any]] = []
            for entity_id in entities:
                candidates = [
                    record
                    for record in self._db.feature_values
                    if record.feature_name == name
                    and record.feature_version == version
                    and record.entity_id == entity_id
                    and record.event_ts <= cutoff
                ]
                if not candidates:
                    continue
                latest = max(candidates, key=lambda record: record.event_ts)
                results.append(
                    {
                        "entity_id": latest.entity_id,
                        "value": latest.value,
                        "event_ts": latest.event_ts,
                        "lineage": latest.lineage,
                    }
                )
            return results
        return []


class _FakeConnectionManager:
    def __init__(self, db: _FakeDatabase) -> None:
        self._db = db

    async def __aenter__(self) -> _FakeConnection:
        return _FakeConnection(self._db)

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakePool:
    def __init__(self) -> None:
        self._db = _FakeDatabase()

    def acquire(self) -> _FakeConnectionManager:
        return _FakeConnectionManager(self._db)

    @property
    def database(self) -> _FakeDatabase:
        return self._db


@pytest.mark.asyncio
async def test_streaming_pipeline_emits_broker_events_on_tick_batches() -> None:
    broker = _FakeBroker()
    captured_service: _CapturingKafkaService | None = None

    def factory(
        config: KafkaIngestionConfig, *, tick_handler, lag_handler=None
    ) -> _CapturingKafkaService:
        nonlocal captured_service
        captured_service = _CapturingKafkaService(
            config, tick_handler=tick_handler, lag_handler=lag_handler
        )
        return captured_service

    pipeline = StreamingIngestionPipeline(
        kafka_config=KafkaIngestionConfig(
            topic="tradepulse.market.ticks",
            bootstrap_servers="kafka:9092",
            group_id="integration",
        ),
        message_broker=broker,
        kafka_service_factory=factory,
        tick_event_topic="tradepulse.data.tick_batch.persisted",
    )

    assert captured_service is not None

    await pipeline.start()
    assert broker.started == 1
    assert captured_service.started is True

    tick = PriceTick.create(
        symbol="BTCUSD",
        venue="BINANCE",
        price=100.5,
        volume=1.0,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        instrument_type=InstrumentType.SPOT,
    )
    await captured_service.tick_handler([tick])

    assert len(broker.messages) == 1
    message = broker.messages[0]
    payload = json.loads(message.payload.decode("utf-8"))
    assert payload["event_type"] == "data.tick_batch.persisted"
    assert payload["symbol"] == "BTC/USD"
    assert payload["venue"] == "BINANCE"
    assert message.topic == "tradepulse.data.tick_batch.persisted"
    assert message.headers == {
        "event_type": "data.tick_batch.persisted",
        "symbol": "BTC/USD",
        "venue": "BINANCE",
        "timeframe": "1min",
    }

    await pipeline.stop()
    assert captured_service.stopped is True
    assert broker.stopped == 1


@pytest.mark.asyncio
async def test_polygon_adapter_fetches_data_with_authorised_requests() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer test-key"
        params = dict(request.url.params)
        assert params["adjusted"] == "true"
        assert params["limit"] == "5000"
        payload = {
            "results": [
                {"t": 1_700_000_000_000, "c": 101.25, "v": 3.5},
            ]
        }
        return httpx.Response(200, json=payload)

    adapter = PolygonIngestionAdapter(api_key="test-key")
    original_client = adapter._client
    original_headers = dict(original_client.headers)
    base_url = original_client.base_url
    await original_client.aclose()
    adapter._client = httpx.AsyncClient(
        base_url=base_url,
        headers=original_headers,
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    try:
        ticks = await adapter.fetch(
            symbol="BTCUSD",
            start="2024-01-01",
            end="2024-01-02",
        )
    finally:
        await adapter.aclose()

    assert requests
    request = requests[0]
    assert (
        request.url.path
        == "/v2/aggs/ticker/BTCUSD/range/1/minute/2024-01-01/2024-01-02"
    )
    assert len(ticks) == 1
    tick = ticks[0]
    assert isinstance(tick, PriceTick)
    assert tick.metadata.symbol == "BTC/USD"
    assert tick.metadata.venue == "POLYGON"
    assert (
        tick.price
        == PriceTick.create(
            symbol="BTCUSD",
            venue="POLYGON",
            price=101.25,
            timestamp=datetime.fromtimestamp(1_700_000_000, tz=timezone.utc),
        ).price
    )


@pytest.mark.asyncio
async def test_feature_store_persists_records_to_redis_and_timescale() -> None:
    redis = _FakeRedis()
    pool = _FakePool()
    store = RealTimeFeatureStore(redis=redis, timescale_pool=pool)

    descriptor = FeatureDescriptor(
        name="alpha_signal",
        version="1",
        entity="portfolio",
        ttl=timedelta(seconds=1),
        description="Integration descriptor",
    )
    lineage = FeatureLineage(
        sources=("pipeline",),
        transformations=("ema",),
        owners=("ml-team",),
    )

    event_ts = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
    record = await store.publish_incremental_update(
        descriptor,
        entity_id="btc-usd",
        value={"score": 0.42},
        event_ts=event_ts,
        lineage=lineage,
    )

    cache_key = descriptor.cache_key("btc-usd")
    assert cache_key in redis.store
    cached_payload = json.loads(redis.store[cache_key])
    assert cached_payload["feature_name"] == descriptor.name
    assert json.loads(cached_payload["value"])["score"] == pytest.approx(0.42)

    db_values = pool.database.feature_values
    assert len(db_values) == 1
    stored = db_values[0]
    assert stored.entity_id == "btc-usd"
    assert stored.value["score"] == pytest.approx(0.42)
    assert record.event_ts == event_ts

    fetched = await store.get_feature(descriptor, "btc-usd")
    assert fetched is not None
    assert fetched.value["score"] == pytest.approx(0.42)

    stream_records = await store.stream_updates(
        descriptor,
        last_id="0-0",
        count=10,
        block_ms=0,
    )
    assert len(stream_records) == 1
    assert stream_records[0].entity_id == "btc-usd"
    assert stream_records[0].value["score"] == pytest.approx(0.42)

    await store.backfill_online_from_offline(
        descriptor,
        entity_ids=["btc-usd"],
        cutoff=event_ts + timedelta(minutes=5),
    )

    assert cache_key in redis.store
