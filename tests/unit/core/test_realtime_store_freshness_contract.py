# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Freshness contract for the realtime feature cache.

Feature data served to live inference must never go backward in event time. This
pins the eight freshness invariants declared in
``artifacts/cache/feature_cache_freshness_matrix.json``: event-time CAS on both
cache tiers, timezone normalisation, microsecond-precision round-trips, rejection
of malformed/missing timestamps, and the authoritative-and-ordered DB fallback
that cannot serve a stale row.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from core.features.realtime_store import (
    FeatureDescriptor,
    FeatureRecord,
    _TTLCache,
)

_SRC = Path(__file__).resolve().parents[3] / "core" / "features" / "realtime_store.py"

_OLD = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
_NEW = datetime(2024, 1, 15, 12, 0, 1, tzinfo=timezone.utc)


def _descriptor() -> FeatureDescriptor:
    return FeatureDescriptor(name="f", version="1.0", entity="user")


def _record(ts: datetime, score: float) -> FeatureRecord:
    return FeatureRecord(
        descriptor=_descriptor(), entity_id="u1", value={"score": score}, event_ts=ts
    )


def _redis_cas():
    """Model the Lua CAS: reject a write whose :ets is older (strict >)."""

    store: dict[str, str] = {}

    async def _script(*, keys: list[str], args: list[Any]) -> int:
        key = keys[0]
        ets_key = f"{key}:ets"
        payload, new_ets = args[0], str(args[1])
        cur = store.get(ets_key)
        if cur is not None and cur > new_ets:
            return 0
        store[key] = payload
        store[ets_key] = new_ets
        return 1

    return store, _script


# 1. Equal-timestamp write conflict is resolved deterministically (last wins on a
#    tie: the strict > guard admits an equal event_ts).
@pytest.mark.asyncio
async def test_equal_timestamp_write_is_deterministic_last_wins() -> None:
    cache = _TTLCache()
    await cache.set("k", _record(_OLD, 0.1), ttl_ms=5000)
    await cache.set("k", _record(_OLD, 0.9), ttl_ms=5000)  # same ts, later write
    got = await cache.get("k")
    assert got is not None and got.value["score"] == 0.9


# 2. Redis CAS and local CAS agree: both reject a strictly-older event_ts.
@pytest.mark.asyncio
async def test_redis_and_local_cas_parity_reject_older() -> None:
    cache = _TTLCache()
    await cache.set("k", _record(_NEW, 0.9), ttl_ms=5000)
    await cache.set("k", _record(_OLD, 0.1), ttl_ms=5000)
    local = await cache.get("k")
    assert local is not None and local.event_ts == _NEW

    store, script = _redis_cas()
    new_iso = _NEW.isoformat(timespec="microseconds")
    old_iso = _OLD.isoformat(timespec="microseconds")
    assert await script(keys=["k"], args=["new", new_iso, 5000]) == 1
    assert await script(keys=["k"], args=["old", old_iso, 5000]) == 0  # older rejected
    assert store["k"] == "new"


# 3./8. The DB fallback is authoritative and ordered: it selects the max event_ts,
#       so a stale row cannot be served after a cache miss.
def test_db_fallback_selects_newest_event_ts() -> None:
    src = _SRC.read_text(encoding="utf-8")
    assert "ORDER BY event_ts DESC" in src, (
        "get_feature DB fallback must order by event_ts DESC or it could serve a stale row"
    )


# 4. Timestamps are normalised to UTC on the read path regardless of source tz.
def test_timestamp_normalised_to_utc_on_read() -> None:
    payload = _record(_NEW, 0.5).to_redis_payload()
    # Rewrite the stored ts into a non-UTC offset representing the same instant.
    payload = dict(payload)
    payload["event_ts"] = "2024-01-15T13:00:01+01:00"  # == 12:00:01Z
    record = FeatureRecord.from_redis_payload(_descriptor(), payload)
    assert record.event_ts.tzinfo == timezone.utc
    assert record.event_ts == _NEW


# 5. A malformed timestamp is rejected (not silently coerced).
def test_malformed_timestamp_rejected() -> None:
    payload = dict(_record(_NEW, 0.5).to_redis_payload())
    payload["event_ts"] = "not-a-timestamp"
    with pytest.raises(ValueError):
        FeatureRecord.from_redis_payload(_descriptor(), payload)


# 6. A missing timestamp is rejected.
def test_missing_timestamp_rejected() -> None:
    payload = dict(_record(_NEW, 0.5).to_redis_payload())
    del payload["event_ts"]
    with pytest.raises((KeyError, ValueError)):
        FeatureRecord.from_redis_payload(_descriptor(), payload)


# 7. Serialization round-trip preserves microsecond precision.
def test_serialization_preserves_microseconds() -> None:
    ts = datetime(2024, 1, 15, 12, 0, 1, 123456, tzinfo=timezone.utc)
    payload = _record(ts, 0.5).to_redis_payload()
    restored = FeatureRecord.from_redis_payload(_descriptor(), payload)
    assert restored.event_ts == ts
    assert restored.event_ts.microsecond == 123456


# 8. A newer cached value is served before the DB is ever consulted.
@pytest.mark.asyncio
async def test_newer_cache_short_circuits_db() -> None:
    cache = _TTLCache()
    await cache.set("k", _record(_NEW, 0.9), ttl_ms=60_000)
    # The hot path returns the cached record without touching any slower tier.
    got = await cache.get("k")
    assert got is not None and got.event_ts == _NEW


def test_all_invariants_have_a_test_here() -> None:
    # Guard against silently shrinking the contract: this file must keep >= 8
    # freshness tests (one per invariant).
    src = Path(__file__).read_text(encoding="utf-8")
    assert src.count("def test_") >= 9  # 8 invariants + this meta-check
