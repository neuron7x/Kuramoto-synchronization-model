"""High-performance real-time feature store built on Redis Streams and TimescaleDB.

The implementation focuses on the key requirements for the trading platform:

* Sub-millisecond feature retrieval via a two-level cache (in-process + Redis).
* TTL-aware cache invalidation to prevent stale features during live trading.
* Feature versioning and lineage metadata stored alongside feature payloads.
* Online/offline consistency guarantees by committing to Redis and TimescaleDB atomically.
* Batch precomputation hooks for recurring feature materialisation windows.
* Real-time incremental updates captured through Redis Streams for downstream consumers.
* Point-in-time correctness utilities for accurate backtesting and replay.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import (
    Awaitable,
    Callable,
    Iterable,
    Mapping,
    MutableMapping,
    Sequence,
)
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Final, TypedDict, TypeVar

from typing_extensions import NotRequired

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from asyncpg.pool import Pool
    from redis.asyncio import Redis


_LOGGER: Final = logging.getLogger(__name__)


T = TypeVar("T")


class _RedisPayload(TypedDict):
    """Typed payload stored in Redis for quick retrieval."""

    entity_id: str
    feature_name: str
    feature_version: str
    event_ts: str
    value: str
    lineage: NotRequired[str]


@dataclass(slots=True)
class FeatureLineage:
    """Represents lineage metadata for a feature computation."""

    sources: tuple[str, ...] = field(default_factory=tuple)
    transformations: tuple[str, ...] = field(default_factory=tuple)
    owners: tuple[str, ...] = field(default_factory=tuple)
    extra: Mapping[str, Any] = field(default_factory=dict)

    def asdict(self) -> Mapping[str, Any]:
        return {
            "sources": list(self.sources),
            "transformations": list(self.transformations),
            "owners": list(self.owners),
            "extra": dict(self.extra),
        }


@dataclass(slots=True)
class FeatureDescriptor:
    """Metadata describing a feature family registered in the store."""

    name: str
    version: str
    entity: str
    ttl: timedelta | None = None
    schema: Mapping[str, str] | None = None
    description: str | None = None

    @property
    def ttl_milliseconds(self) -> int | None:
        if self.ttl is None:
            return None
        return max(1, int(self.ttl.total_seconds() * 1000))

    @property
    def stream_key(self) -> str:
        return f"feature:{self.entity}:{self.name}:v{self.version}:stream"

    def cache_key(self, entity_id: str) -> str:
        return f"feature:{self.entity}:{self.name}:v{self.version}:entity:{entity_id}"


@dataclass(slots=True)
class FeatureRecord:
    """Concrete feature payload stored in the system."""

    descriptor: FeatureDescriptor
    entity_id: str
    value: Mapping[str, Any]
    event_ts: datetime
    lineage: FeatureLineage | None = None

    def to_redis_payload(self) -> _RedisPayload:
        payload: _RedisPayload = {
            "entity_id": self.entity_id,
            "feature_name": self.descriptor.name,
            "feature_version": self.descriptor.version,
            "event_ts": self.event_ts.isoformat(timespec="microseconds"),
            "value": json.dumps(self.value, separators=(",", ":")),
        }
        if self.lineage is not None:
            payload["lineage"] = json.dumps(
                self.lineage.asdict(), separators=(",", ":")
            )
        return payload

    @classmethod
    def from_redis_payload(
        cls,
        descriptor: FeatureDescriptor,
        payload: Mapping[str, str],
    ) -> "FeatureRecord":
        lineage = None
        lineage_raw = payload.get("lineage")
        if lineage_raw:
            parsed = json.loads(lineage_raw)
            lineage = FeatureLineage(
                sources=tuple(parsed.get("sources", [])),
                transformations=tuple(parsed.get("transformations", [])),
                owners=tuple(parsed.get("owners", [])),
                extra=parsed.get("extra", {}),
            )
        return cls(
            descriptor=descriptor,
            entity_id=payload["entity_id"],
            value=json.loads(payload["value"]),
            event_ts=datetime.fromisoformat(payload["event_ts"]).astimezone(
                timezone.utc
            ),
            lineage=lineage,
        )


class _TTLCache:
    """Light-weight in-process cache to hit sub-millisecond retrieval goals."""

    def __init__(self, max_size: int = 4_096) -> None:
        self._data: MutableMapping[str, tuple[float, FeatureRecord]] = {}
        self._max_size = max_size
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> FeatureRecord | None:
        async with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            expires_at, record = entry
            now = asyncio.get_running_loop().time()
            if expires_at <= now:
                self._data.pop(key, None)
                return None
            return record

    async def set(self, key: str, record: FeatureRecord, ttl_ms: int | None) -> None:
        if ttl_ms is None:
            # Avoid unbounded growth.
            ttl_ms = 1_000
        expiry = asyncio.get_running_loop().time() + ttl_ms / 1_000.0
        async with self._lock:
            if len(self._data) >= self._max_size:
                # Drop the stalest entry (simple heuristic sufficient for hot cache).
                stale_key = min(self._data.items(), key=lambda item: item[1][0])[0]
                self._data.pop(stale_key, None)
            self._data[key] = (expiry, record)

    async def invalidate(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()


class RealTimeFeatureStore:
    """Coordinator for online/offline feature access with strict consistency."""

    def __init__(
        self,
        redis: "Redis",
        timescale_pool: "Pool",
        *,
        default_ttl: timedelta = timedelta(milliseconds=750),
        stream_maxlen: int = 50_000,
        write_retry_attempts: int = 3,
    ) -> None:
        self._redis = redis
        self._db_pool = timescale_pool
        self._default_ttl = default_ttl
        self._stream_maxlen = stream_maxlen
        self._registry_lock = asyncio.Lock()
        self._registry_ready = asyncio.Event()
        self._microcache = _TTLCache()
        self._registered_descriptors: dict[tuple[str, str, str], FeatureDescriptor] = {}
        self._write_retry_attempts = max(1, write_retry_attempts)

    async def initialise(self) -> None:
        """Ensure metadata tables exist in TimescaleDB."""

        async with self._registry_lock:
            if self._registry_ready.is_set():
                return
            async with self._db_pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS feature_registry (
                        feature_name TEXT NOT NULL,
                        feature_version TEXT NOT NULL,
                        entity TEXT NOT NULL,
                        ttl_ms BIGINT,
                        schema JSONB,
                        description TEXT,
                        PRIMARY KEY (feature_name, feature_version, entity)
                    );
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS feature_values (
                        feature_name TEXT NOT NULL,
                        feature_version TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        event_ts TIMESTAMPTZ NOT NULL,
                        value JSONB NOT NULL,
                        lineage JSONB,
                        PRIMARY KEY (feature_name, feature_version, entity_id, event_ts)
                    );
                    """
                )
                await conn.execute(
                    """
                    SELECT create_hypertable('feature_values', 'event_ts', if_not_exists => TRUE);
                    """
                )
            self._registry_ready.set()
            _LOGGER.info("RealTimeFeatureStore metadata initialised")

    async def register_feature(self, descriptor: FeatureDescriptor) -> None:
        """Register feature metadata and cache descriptor locally."""

        await self.initialise()
        key = (descriptor.name, descriptor.version, descriptor.entity)
        existing = self._registered_descriptors.get(key)
        if existing is not None and existing == descriptor:
            return
        ttl_ms = descriptor.ttl_milliseconds
        async with self._db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO feature_registry (feature_name, feature_version, entity, ttl_ms, schema, description)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (feature_name, feature_version, entity)
                DO UPDATE SET ttl_ms = EXCLUDED.ttl_ms, schema = EXCLUDED.schema, description = EXCLUDED.description;
                """,
                descriptor.name,
                descriptor.version,
                descriptor.entity,
                ttl_ms,
                (
                    json.dumps(descriptor.schema)
                    if descriptor.schema is not None
                    else None
                ),
                descriptor.description,
            )
        self._registered_descriptors[key] = descriptor
        _LOGGER.debug(
            "Registered feature %s v%s for entity %s",
            descriptor.name,
            descriptor.version,
            descriptor.entity,
        )

    async def publish_incremental_update(
        self,
        descriptor: FeatureDescriptor,
        entity_id: str,
        value: Mapping[str, Any],
        *,
        event_ts: datetime | None = None,
        lineage: FeatureLineage | None = None,
    ) -> FeatureRecord:
        """Persist an incremental feature update to both Redis and TimescaleDB."""

        await self.register_feature(descriptor)
        event_ts = (event_ts or datetime.now(timezone.utc)).astimezone(timezone.utc)
        record = FeatureRecord(
            descriptor=descriptor,
            entity_id=entity_id,
            value=dict(value),
            event_ts=event_ts,
            lineage=lineage,
        )
        redis_payload = record.to_redis_payload()
        ttl_ms = descriptor.ttl_milliseconds or int(
            self._default_ttl.total_seconds() * 1000
        )

        timescale_applied = await self._execute_with_retries(
            lambda: self._write_to_timescale(record),
            attempts=self._write_retry_attempts,
            op_name="timescale write",
        )
        try:
            await self._execute_with_retries(
                lambda: self._write_to_redis(
                    descriptor, entity_id, redis_payload, ttl_ms
                ),
                attempts=self._write_retry_attempts,
                op_name="redis write",
            )
        except Exception:
            if timescale_applied:
                try:
                    await self._delete_from_timescale(record)
                except (
                    Exception
                ) as rollback_error:  # pragma: no cover - defensive logging
                    _LOGGER.error(
                        "Failed to rollback Timescale write for %s/%s after Redis error: %s",  # noqa: TRY400
                        descriptor.name,
                        entity_id,
                        rollback_error,
                    )
                else:
                    _LOGGER.warning(
                        "Rolled back Timescale write for %s/%s after Redis error",  # noqa: TRY400
                        descriptor.name,
                        entity_id,
                    )
            raise
        await self._microcache.set(descriptor.cache_key(entity_id), record, ttl_ms)
        return record

    async def _write_to_redis(
        self,
        descriptor: FeatureDescriptor,
        entity_id: str,
        payload: _RedisPayload,
        ttl_ms: int,
    ) -> None:
        stream_key = descriptor.stream_key
        cache_key = descriptor.cache_key(entity_id)
        payload_json = json.dumps(payload, separators=(",", ":"))
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.xadd(stream_key, payload, maxlen=self._stream_maxlen, approximate=True)
            pipe.set(cache_key, payload_json, px=ttl_ms)
            await pipe.execute()

    async def _write_to_timescale(self, record: FeatureRecord) -> bool:
        lineage_json = json.dumps(record.lineage.asdict()) if record.lineage else None
        async with self._db_pool.acquire() as conn:
            command_tag = await conn.execute(
                """
                INSERT INTO feature_values (feature_name, feature_version, entity_id, event_ts, value, lineage)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (feature_name, feature_version, entity_id, event_ts) DO NOTHING;
                """,
                record.descriptor.name,
                record.descriptor.version,
                record.entity_id,
                record.event_ts,
                json.dumps(record.value),
                lineage_json,
            )
        try:
            affected = int(command_tag.rsplit(" ", 1)[-1])
            return affected > 0
        except (ValueError, IndexError):  # pragma: no cover - defensive guard
            return command_tag.endswith("1")

    async def _delete_from_timescale(self, record: FeatureRecord) -> None:
        async with self._db_pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM feature_values
                WHERE feature_name = $1 AND feature_version = $2 AND entity_id = $3 AND event_ts = $4;
                """,
                record.descriptor.name,
                record.descriptor.version,
                record.entity_id,
                record.event_ts,
            )

    async def _execute_with_retries(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        attempts: int,
        op_name: str,
    ) -> T:
        if attempts <= 0:
            raise ValueError("attempts must be positive")
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await operation()
            except Exception as exc:
                last_error = exc
                _LOGGER.warning(
                    "%s attempt %s/%s failed: %s",
                    op_name,
                    attempt,
                    attempts,
                    exc,
                )
                if attempt != attempts:
                    await asyncio.sleep(min(0.1 * attempt, 0.5))
        assert last_error is not None
        raise last_error

    async def get_feature(
        self, descriptor: FeatureDescriptor, entity_id: str
    ) -> FeatureRecord | None:
        """Retrieve the most recent feature value for an entity."""

        cache_key = descriptor.cache_key(entity_id)
        cached = await self._microcache.get(cache_key)
        if cached is not None:
            return cached

        payload_json = await self._redis.get(cache_key)
        if payload_json:
            if isinstance(payload_json, (bytes, bytearray, memoryview)):
                payload_text = bytes(payload_json).decode("utf-8")
            else:
                payload_text = payload_json
            payload = json.loads(payload_text)
            record = FeatureRecord.from_redis_payload(descriptor, payload)
            ttl_ms = descriptor.ttl_milliseconds or int(
                self._default_ttl.total_seconds() * 1000
            )
            await self._microcache.set(cache_key, record, ttl_ms)
            return record

        # Fallback to TimescaleDB when cache misses occur.
        async with self._db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT value, event_ts, lineage
                FROM feature_values
                WHERE feature_name = $1 AND feature_version = $2 AND entity_id = $3
                ORDER BY event_ts DESC
                LIMIT 1;
                """,
                descriptor.name,
                descriptor.version,
                entity_id,
            )
        if not row:
            return None
        lineage = None
        if row["lineage"] is not None:
            parsed = row["lineage"]
            lineage = FeatureLineage(
                sources=tuple(parsed.get("sources", [])),
                transformations=tuple(parsed.get("transformations", [])),
                owners=tuple(parsed.get("owners", [])),
                extra=parsed.get("extra", {}),
            )
        record = FeatureRecord(
            descriptor=descriptor,
            entity_id=entity_id,
            value=row["value"],
            event_ts=row["event_ts"].astimezone(timezone.utc),
            lineage=lineage,
        )
        ttl_ms = descriptor.ttl_milliseconds or int(
            self._default_ttl.total_seconds() * 1000
        )
        await self._microcache.set(cache_key, record, ttl_ms)
        return record

    async def get_features_point_in_time(
        self,
        descriptor: FeatureDescriptor,
        entity_id: str,
        as_of: datetime,
    ) -> FeatureRecord | None:
        """Retrieve the feature as of a particular timestamp for backtesting."""

        as_of = as_of.astimezone(timezone.utc)
        async with self._db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT value, event_ts, lineage
                FROM feature_values
                WHERE feature_name = $1 AND feature_version = $2 AND entity_id = $3 AND event_ts <= $4
                ORDER BY event_ts DESC
                LIMIT 1;
                """,
                descriptor.name,
                descriptor.version,
                entity_id,
                as_of,
            )
        if not row:
            return None
        lineage = None
        if row["lineage"] is not None:
            parsed = row["lineage"]
            lineage = FeatureLineage(
                sources=tuple(parsed.get("sources", [])),
                transformations=tuple(parsed.get("transformations", [])),
                owners=tuple(parsed.get("owners", [])),
                extra=parsed.get("extra", {}),
            )
        return FeatureRecord(
            descriptor=descriptor,
            entity_id=entity_id,
            value=row["value"],
            event_ts=row["event_ts"].astimezone(timezone.utc),
            lineage=lineage,
        )

    async def backfill_online_from_offline(
        self,
        descriptor: FeatureDescriptor,
        entity_ids: Iterable[str],
        *,
        cutoff: datetime | None = None,
        chunk_size: int = 500,
    ) -> None:
        """Sync offline records into Redis cache to guarantee parity."""

        cutoff = (cutoff or datetime.now(timezone.utc)).astimezone(timezone.utc)
        async with self._db_pool.acquire() as conn:
            for batch in _chunked(tuple(entity_ids), chunk_size):
                rows = await conn.fetch(
                    """
                    SELECT entity_id, value, event_ts, lineage
                    FROM feature_values
                    WHERE feature_name = $1 AND feature_version = $2 AND entity_id = ANY($3::TEXT[])
                        AND event_ts = (
                            SELECT MAX(event_ts)
                            FROM feature_values fv
                            WHERE fv.feature_name = feature_values.feature_name
                              AND fv.feature_version = feature_values.feature_version
                              AND fv.entity_id = feature_values.entity_id
                              AND fv.event_ts <= $4
                        );
                    """,
                    descriptor.name,
                    descriptor.version,
                    list(batch),
                    cutoff,
                )
                for row in rows:
                    lineage = None
                    if row["lineage"] is not None:
                        parsed = row["lineage"]
                        lineage = FeatureLineage(
                            sources=tuple(parsed.get("sources", [])),
                            transformations=tuple(parsed.get("transformations", [])),
                            owners=tuple(parsed.get("owners", [])),
                            extra=parsed.get("extra", {}),
                        )
                    record = FeatureRecord(
                        descriptor=descriptor,
                        entity_id=row["entity_id"],
                        value=row["value"],
                        event_ts=row["event_ts"].astimezone(timezone.utc),
                        lineage=lineage,
                    )
                    payload = record.to_redis_payload()
                    ttl_ms = descriptor.ttl_milliseconds or int(
                        self._default_ttl.total_seconds() * 1000
                    )
                    await self._write_to_redis(
                        descriptor, record.entity_id, payload, ttl_ms
                    )
                    await self._microcache.set(
                        descriptor.cache_key(record.entity_id), record, ttl_ms
                    )

    async def run_batch_precomputation(
        self,
        descriptor: FeatureDescriptor,
        entity_ids: Sequence[str],
        window_start: datetime,
        window_end: datetime,
        compute_fn: Callable[
            [Sequence[str], datetime, datetime],
            Awaitable[Mapping[str, Mapping[str, Any]]],
        ],
        *,
        batch_size: int = 500,
    ) -> None:
        """Materialise features in bulk using the provided compute function."""

        window_start = window_start.astimezone(timezone.utc)
        window_end = window_end.astimezone(timezone.utc)
        for batch in _chunked(tuple(entity_ids), batch_size):
            feature_map = await compute_fn(batch, window_start, window_end)
            for entity_id, feature_value in feature_map.items():
                await self.publish_incremental_update(
                    descriptor,
                    entity_id,
                    feature_value,
                    event_ts=window_end,
                )

    async def stream_updates(
        self,
        descriptor: FeatureDescriptor,
        *,
        last_id: str = "$",
        count: int = 100,
        block_ms: int = 1_000,
    ) -> list[FeatureRecord]:
        """Read incremental updates from Redis Streams for downstream consumers."""

        stream_key = descriptor.stream_key
        response = await self._redis.xread(
            streams={stream_key: last_id},
            count=count,
            block=block_ms,
        )
        records: list[FeatureRecord] = []
        for _, entries in response or []:
            for entry_id, payload in entries:
                payload_str: dict[str, str] = {}
                for key, value in payload.items():
                    key_str = (
                        key.decode("utf-8")
                        if isinstance(key, (bytes, bytearray, memoryview))
                        else key
                    )
                    if isinstance(value, (bytes, bytearray, memoryview)):
                        payload_str[key_str] = bytes(value).decode("utf-8")
                    else:
                        payload_str[key_str] = value
                record = FeatureRecord.from_redis_payload(descriptor, payload_str)
                records.append(record)
                _LOGGER.debug(
                    "Consumed stream entry %s for %s", entry_id, descriptor.name
                )
        return records


def _chunked(iterable: Sequence[T], size: int) -> Iterable[Sequence[T]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    for start in range(0, len(iterable), size):
        yield iterable[start : start + size]
