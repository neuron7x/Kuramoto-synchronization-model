# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for core/features/realtime_store.py."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.features.realtime_store import (
    FeatureDescriptor,
    FeatureLineage,
    FeatureRecord,
    _TTLCache,
)


class TestFeatureLineage:
    """Tests for FeatureLineage dataclass."""

    def test_default_values(self) -> None:
        """Verify default values are empty."""
        lineage = FeatureLineage()

        assert lineage.sources == ()
        assert lineage.transformations == ()
        assert lineage.owners == ()
        assert lineage.extra == {}

    def test_custom_values(self) -> None:
        """Verify custom values are stored correctly."""
        lineage = FeatureLineage(
            sources=("src1", "src2"),
            transformations=("transform1",),
            owners=("team_a",),
            extra={"custom": "value"},
        )

        assert lineage.sources == ("src1", "src2")
        assert lineage.transformations == ("transform1",)
        assert lineage.owners == ("team_a",)
        assert lineage.extra == {"custom": "value"}

    def test_asdict(self) -> None:
        """Verify asdict returns proper dictionary structure."""
        lineage = FeatureLineage(
            sources=("src1",),
            transformations=("transform1",),
            owners=("team_a",),
            extra={"key": "val"},
        )

        result = lineage.asdict()

        assert result == {
            "sources": ["src1"],
            "transformations": ["transform1"],
            "owners": ["team_a"],
            "extra": {"key": "val"},
        }

    def test_asdict_returns_lists(self) -> None:
        """Verify asdict converts tuples to lists."""
        lineage = FeatureLineage(sources=("a", "b"))

        result = lineage.asdict()

        assert isinstance(result["sources"], list)


class TestFeatureDescriptor:
    """Tests for FeatureDescriptor dataclass."""

    def test_required_fields(self) -> None:
        """Verify required fields are set correctly."""
        descriptor = FeatureDescriptor(
            name="test_feature",
            version="1.0",
            entity="user",
        )

        assert descriptor.name == "test_feature"
        assert descriptor.version == "1.0"
        assert descriptor.entity == "user"

    def test_optional_fields_defaults(self) -> None:
        """Verify optional fields have proper defaults."""
        descriptor = FeatureDescriptor(
            name="test",
            version="1.0",
            entity="user",
        )

        assert descriptor.ttl is None
        assert descriptor.schema is None
        assert descriptor.description is None

    def test_ttl_milliseconds_none(self) -> None:
        """Verify ttl_milliseconds returns None when ttl is None."""
        descriptor = FeatureDescriptor(
            name="test",
            version="1.0",
            entity="user",
        )

        assert descriptor.ttl_milliseconds is None

    def test_ttl_milliseconds_conversion(self) -> None:
        """Verify ttl_milliseconds converts correctly."""
        descriptor = FeatureDescriptor(
            name="test",
            version="1.0",
            entity="user",
            ttl=timedelta(seconds=5),
        )

        assert descriptor.ttl_milliseconds == 5000

    def test_ttl_milliseconds_minimum(self) -> None:
        """Verify ttl_milliseconds returns at least 1."""
        descriptor = FeatureDescriptor(
            name="test",
            version="1.0",
            entity="user",
            ttl=timedelta(microseconds=1),
        )

        assert descriptor.ttl_milliseconds >= 1

    def test_stream_key(self) -> None:
        """Verify stream_key format."""
        descriptor = FeatureDescriptor(
            name="test_feature",
            version="1.0",
            entity="user",
        )

        assert descriptor.stream_key == "feature:user:test_feature:v1.0:stream"

    def test_cache_key(self) -> None:
        """Verify cache_key format."""
        descriptor = FeatureDescriptor(
            name="test_feature",
            version="1.0",
            entity="user",
        )

        key = descriptor.cache_key("user123")

        assert key == "feature:user:test_feature:v1.0:entity:user123"


class TestFeatureRecord:
    """Tests for FeatureRecord dataclass."""

    @pytest.fixture
    def descriptor(self) -> FeatureDescriptor:
        """Create a test descriptor."""
        return FeatureDescriptor(
            name="test_feature",
            version="1.0",
            entity="user",
        )

    @pytest.fixture
    def record(self, descriptor: FeatureDescriptor) -> FeatureRecord:
        """Create a test record."""
        return FeatureRecord(
            descriptor=descriptor,
            entity_id="user123",
            value={"score": 0.95},
            event_ts=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        )

    def test_to_redis_payload_basic(
        self, record: FeatureRecord, descriptor: FeatureDescriptor
    ) -> None:
        """Verify to_redis_payload generates correct payload."""
        payload = record.to_redis_payload()

        assert payload["entity_id"] == "user123"
        assert payload["feature_name"] == "test_feature"
        assert payload["feature_version"] == "1.0"
        assert "event_ts" in payload
        assert payload["value"] == '{"score":0.95}'

    def test_to_redis_payload_with_lineage(self, descriptor: FeatureDescriptor) -> None:
        """Verify to_redis_payload includes lineage when present."""
        lineage = FeatureLineage(sources=("src1",))
        record = FeatureRecord(
            descriptor=descriptor,
            entity_id="user123",
            value={"score": 0.95},
            event_ts=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            lineage=lineage,
        )

        payload = record.to_redis_payload()

        assert "lineage" in payload
        lineage_parsed = json.loads(payload["lineage"])
        assert lineage_parsed["sources"] == ["src1"]

    def test_from_redis_payload_basic(self, descriptor: FeatureDescriptor) -> None:
        """Verify from_redis_payload reconstructs record correctly."""
        payload = {
            "entity_id": "user123",
            "feature_name": "test_feature",
            "feature_version": "1.0",
            "event_ts": "2024-01-15T12:00:00.000000+00:00",
            "value": '{"score":0.95}',
        }

        record = FeatureRecord.from_redis_payload(descriptor, payload)

        assert record.entity_id == "user123"
        assert record.value == {"score": 0.95}
        assert record.event_ts == datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert record.lineage is None

    def test_from_redis_payload_with_lineage(self, descriptor: FeatureDescriptor) -> None:
        """Verify from_redis_payload parses lineage correctly."""
        lineage_data = {
            "sources": ["src1"],
            "transformations": [],
            "owners": [],
            "extra": {},
        }
        payload = {
            "entity_id": "user123",
            "feature_name": "test_feature",
            "feature_version": "1.0",
            "event_ts": "2024-01-15T12:00:00.000000+00:00",
            "value": '{"score":0.95}',
            "lineage": json.dumps(lineage_data),
        }

        record = FeatureRecord.from_redis_payload(descriptor, payload)

        assert record.lineage is not None
        assert record.lineage.sources == ("src1",)


class TestTTLCache:
    """Tests for _TTLCache class."""

    @pytest.fixture
    def descriptor(self) -> FeatureDescriptor:
        """Create a test descriptor."""
        return FeatureDescriptor(
            name="test",
            version="1.0",
            entity="user",
        )

    @pytest.fixture
    def record(self, descriptor: FeatureDescriptor) -> FeatureRecord:
        """Create a test record."""
        return FeatureRecord(
            descriptor=descriptor,
            entity_id="user123",
            value={"data": "value"},
            event_ts=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_set_and_get(self, record: FeatureRecord) -> None:
        """Verify basic set and get operations."""
        cache = _TTLCache()

        await cache.set("key1", record, ttl_ms=5000)
        result = await cache.get("key1")

        assert result is not None
        assert result.entity_id == record.entity_id

    @pytest.mark.asyncio
    async def test_get_missing_key(self) -> None:
        """Verify get returns None for missing key."""
        cache = _TTLCache()

        result = await cache.get("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate(self, record: FeatureRecord) -> None:
        """Verify invalidate removes the key."""
        cache = _TTLCache()
        await cache.set("key1", record, ttl_ms=5000)

        await cache.invalidate("key1")
        result = await cache.get("key1")

        assert result is None

    @pytest.mark.asyncio
    async def test_clear(self, record: FeatureRecord) -> None:
        """Verify clear removes all keys."""
        cache = _TTLCache()
        await cache.set("key1", record, ttl_ms=5000)
        await cache.set("key2", record, ttl_ms=5000)

        await cache.clear()
        result1 = await cache.get("key1")
        result2 = await cache.get("key2")

        assert result1 is None
        assert result2 is None

    @pytest.mark.asyncio
    async def test_ttl_default_on_none(self, record: FeatureRecord) -> None:
        """Verify TTL defaults to 1 second when None."""
        cache = _TTLCache()

        # Should not raise
        await cache.set("key1", record, ttl_ms=None)
        result = await cache.get("key1")

        assert result is not None

    @pytest.mark.asyncio
    async def test_max_size_eviction(self, descriptor: FeatureDescriptor) -> None:
        """Verify oldest entry is evicted when max size is reached."""
        cache = _TTLCache(max_size=2)

        # Create records with distinct timestamps
        record1 = FeatureRecord(
            descriptor=descriptor,
            entity_id="user1",
            value={},
            event_ts=datetime.now(timezone.utc),
        )
        record2 = FeatureRecord(
            descriptor=descriptor,
            entity_id="user2",
            value={},
            event_ts=datetime.now(timezone.utc),
        )
        record3 = FeatureRecord(
            descriptor=descriptor,
            entity_id="user3",
            value={},
            event_ts=datetime.now(timezone.utc),
        )

        # Set records with varying TTLs - earliest expiry will be evicted first
        # Using significantly different TTLs to ensure deterministic eviction order
        await cache.set("key1", record1, ttl_ms=100)  # Shortest TTL, earliest expiry
        await cache.set("key2", record2, ttl_ms=5000)  # Longer TTL

        # This should evict key1 (earliest expiry) due to max_size=2
        await cache.set("key3", record3, ttl_ms=5000)

        # key1 should be evicted (it had the earliest expiry time)
        result1 = await cache.get("key1")
        result2 = await cache.get("key2")
        result3 = await cache.get("key3")

        assert result1 is None  # Evicted
        assert result2 is not None
        assert result3 is not None


class TestRealTimeFeatureStore:
    """Tests for RealTimeFeatureStore class."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.pipeline = MagicMock()

        pipe = AsyncMock()
        pipe.xadd = MagicMock()
        pipe.set = MagicMock()
        pipe.execute = AsyncMock(return_value=[])
        pipe.__aenter__ = AsyncMock(return_value=pipe)
        pipe.__aexit__ = AsyncMock(return_value=None)
        redis.pipeline.return_value = pipe

        return redis

    @pytest.fixture
    def mock_pool(self) -> AsyncMock:
        """Create a mock asyncpg pool."""
        pool = AsyncMock()

        conn = AsyncMock()
        conn.execute = AsyncMock(return_value="INSERT 0 1")
        conn.fetchrow = AsyncMock(return_value=None)
        conn.fetch = AsyncMock(return_value=[])
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=None)

        pool.acquire = MagicMock(return_value=conn)

        return pool

    @pytest.fixture
    def descriptor(self) -> FeatureDescriptor:
        """Create a test descriptor."""
        return FeatureDescriptor(
            name="test_feature",
            version="1.0",
            entity="user",
            ttl=timedelta(seconds=30),
        )

    @pytest.mark.asyncio
    async def test_store_initialization(self, mock_redis: AsyncMock, mock_pool: AsyncMock) -> None:
        """Verify store initializes correctly."""
        from core.features.realtime_store import RealTimeFeatureStore

        store = RealTimeFeatureStore(mock_redis, mock_pool)

        assert store._redis is mock_redis
        assert store._db_pool is mock_pool

    @pytest.mark.asyncio
    async def test_execute_with_retries_success(
        self, mock_redis: AsyncMock, mock_pool: AsyncMock
    ) -> None:
        """Verify _execute_with_retries succeeds on first attempt."""
        from core.features.realtime_store import RealTimeFeatureStore

        store = RealTimeFeatureStore(mock_redis, mock_pool)

        async def success_op() -> str:
            return "success"

        result = await store._execute_with_retries(success_op, attempts=3, op_name="test")

        assert result == "success"

    @pytest.mark.asyncio
    async def test_execute_with_retries_failure(
        self, mock_redis: AsyncMock, mock_pool: AsyncMock
    ) -> None:
        """Verify _execute_with_retries raises after exhausting attempts."""
        from core.features.realtime_store import RealTimeFeatureStore

        store = RealTimeFeatureStore(mock_redis, mock_pool)
        attempt_count = 0

        async def failing_op() -> None:
            nonlocal attempt_count
            attempt_count += 1
            raise RuntimeError("Failed")

        with pytest.raises(RuntimeError, match="Failed"):
            await store._execute_with_retries(failing_op, attempts=2, op_name="test")

        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_execute_with_retries_invalid_attempts(
        self, mock_redis: AsyncMock, mock_pool: AsyncMock
    ) -> None:
        """Verify _execute_with_retries raises for invalid attempts."""
        from core.features.realtime_store import RealTimeFeatureStore

        store = RealTimeFeatureStore(mock_redis, mock_pool)

        async def dummy_op() -> None:
            pass

        with pytest.raises(ValueError, match="attempts must be positive"):
            await store._execute_with_retries(dummy_op, attempts=0, op_name="test")

    @pytest.mark.asyncio
    async def test_microcache_hit(
        self,
        mock_redis: AsyncMock,
        mock_pool: AsyncMock,
        descriptor: FeatureDescriptor,
    ) -> None:
        """Verify get_feature returns from microcache when available."""
        from core.features.realtime_store import RealTimeFeatureStore

        store = RealTimeFeatureStore(mock_redis, mock_pool)

        # Pre-populate microcache
        record = FeatureRecord(
            descriptor=descriptor,
            entity_id="user123",
            value={"cached": True},
            event_ts=datetime.now(timezone.utc),
        )
        await store._microcache.set(descriptor.cache_key("user123"), record, ttl_ms=5000)

        result = await store.get_feature(descriptor, "user123")

        assert result is not None
        assert result.value == {"cached": True}
        # Redis should not be called
        mock_redis.get.assert_not_called()
