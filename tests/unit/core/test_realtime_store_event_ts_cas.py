# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression: the feature cache must be event_ts-ordered, not last-writer-wins.

Bug: both the in-process microcache and the Redis cache were written keyed on the
entity only, with no ordering guard. A later-arriving OLDER tick (event_ts T1 <
T2) overwrote the newer cached feature, so get_feature (which reads the cache
first) served a stale feature during live trading.

Fix: compare-and-set on event_ts — the microcache skips an older record, and the
Redis write applies a Lua CAS with a companion ``:ets`` key.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from core.features.realtime_store import (
    FeatureDescriptor,
    FeatureRecord,
    RealTimeFeatureStore,
    _TTLCache,
)

_T1 = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
_T2 = datetime(2024, 1, 15, 12, 0, 1, tzinfo=timezone.utc)  # one second newer


def _descriptor() -> FeatureDescriptor:
    return FeatureDescriptor(name="f", version="1.0", entity="user")


def _record(ts: datetime, score: float) -> FeatureRecord:
    return FeatureRecord(
        descriptor=_descriptor(), entity_id="u1", value={"score": score}, event_ts=ts
    )


# --------------------------------------------------------------------------- #
# In-process microcache CAS (the hot read path get_feature hits first)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_microcache_rejects_older_event_ts() -> None:
    cache = _TTLCache()
    await cache.set("k", _record(_T2, 0.9), ttl_ms=5000)
    await cache.set("k", _record(_T1, 0.1), ttl_ms=5000)  # older, arrives late
    got = await cache.get("k")
    assert got is not None and got.event_ts == _T2 and got.value["score"] == 0.9


@pytest.mark.asyncio
async def test_microcache_accepts_newer_event_ts() -> None:
    cache = _TTLCache()
    await cache.set("k", _record(_T1, 0.1), ttl_ms=5000)
    await cache.set("k", _record(_T2, 0.9), ttl_ms=5000)  # newer wins
    got = await cache.get("k")
    assert got is not None and got.event_ts == _T2


# --------------------------------------------------------------------------- #
# Redis CAS (cross-process ordering) via a faithful fake that runs the script
# --------------------------------------------------------------------------- #
class _FakeRedisCas:
    """Minimal fake modelling the Lua CAS + companion :ets key semantics."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def register_script(self, lua: str) -> Any:
        async def _script(*, keys: list[str], args: list[Any]) -> int:
            key = keys[0]
            ets_key = key + ":ets"
            payload, new_ets, _ttl = args[0], str(args[1]), args[2]
            cur = self.store.get(ets_key)
            if cur is not None and cur > new_ets:  # stored is newer -> skip
                return 0
            self.store[key] = payload
            self.store[ets_key] = new_ets
            return 1

        return _script

    def pipeline(self, transaction: bool = False) -> "_FakePipe":
        return _FakePipe()

    async def get(self, key: str) -> str | None:
        return self.store.get(key)


class _FakePipe:
    async def __aenter__(self) -> "_FakePipe":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def xadd(self, *a: object, **k: object) -> None:
        return None

    async def execute(self) -> list[object]:
        return []


def _store(redis: Any) -> RealTimeFeatureStore:
    return RealTimeFeatureStore(redis, timescale_pool=object())


@pytest.mark.asyncio
async def test_redis_cache_rejects_older_event_ts() -> None:
    redis = _FakeRedisCas()
    store = _store(redis)
    d = _descriptor()
    ck = d.cache_key("u1")

    await store._write_to_redis(d, "u1", _record(_T2, 0.9).to_redis_payload(), 5000)
    await store._write_to_redis(d, "u1", _record(_T1, 0.1).to_redis_payload(), 5000)  # older

    stored = json.loads(redis.store[ck])
    assert stored["event_ts"] == _T2.isoformat(timespec="microseconds")
    assert json.loads(stored["value"]) == {"score": 0.9}


@pytest.mark.asyncio
async def test_redis_cache_accepts_newer_event_ts() -> None:
    redis = _FakeRedisCas()
    store = _store(redis)
    d = _descriptor()
    ck = d.cache_key("u1")

    await store._write_to_redis(d, "u1", _record(_T1, 0.1).to_redis_payload(), 5000)
    await store._write_to_redis(d, "u1", _record(_T2, 0.9).to_redis_payload(), 5000)  # newer

    stored = json.loads(redis.store[ck])
    assert stored["event_ts"] == _T2.isoformat(timespec="microseconds")
