# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("GEOSYNC_ADMIN_TOKEN", "test-token")
os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-secret-value")

from application.api import service
from application.api.service import FeatureResponse, TTLCache

pytestmark = pytest.mark.asyncio


class FrozenDateTime:
    def __init__(self, initial: datetime) -> None:
        self._current = initial

    def now(self, tz=None):  # type: ignore[override]
        if tz is None:
            return self._current
        return self._current.astimezone(tz)

    def advance(self, seconds: int | float) -> None:
        self._current += timedelta(seconds=seconds)


@pytest.fixture
def frozen_datetime(monkeypatch) -> "FrozenDateTime":
    frozen = FrozenDateTime(datetime(2024, 1, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(service, "datetime", frozen)
    return frozen


async def test_expired_entry_is_removed(frozen_datetime: "FrozenDateTime") -> None:
    cache = TTLCache(ttl_seconds=10)
    payload = FeatureResponse(symbol="XYZ", features={"value": 1.0})

    await cache.set("key", payload, etag="etag-1")
    frozen_datetime.advance(cache.ttl_seconds + 1)

    assert await cache.get("key") is None
    assert "key" not in cache._entries


async def test_capacity_eviction_removes_oldest_entry(
    frozen_datetime: "FrozenDateTime",
) -> None:
    cache = TTLCache(ttl_seconds=30, max_entries=2)

    payload1 = FeatureResponse(symbol="AAA", features={})
    await cache.set("key-1", payload1, etag="etag-1")

    frozen_datetime.advance(1)
    payload2 = FeatureResponse(symbol="BBB", features={})
    await cache.set("key-2", payload2, etag="etag-2")

    frozen_datetime.advance(1)
    payload3 = FeatureResponse(symbol="CCC", features={})
    await cache.set("key-3", payload3, etag="etag-3")

    assert "key-1" not in cache._entries
    assert set(cache._entries.keys()) == {"key-2", "key-3"}


async def test_get_returns_cached_entry_when_not_expired(
    frozen_datetime: "FrozenDateTime",
) -> None:
    cache = TTLCache(ttl_seconds=60)
    payload = FeatureResponse(symbol="XYZ", features={"value": 42.0})

    await cache.set("key", payload, etag="etag-123")
    entry = await cache.get("key")

    assert entry is not None
    assert entry.payload is payload
    assert entry.etag == "etag-123"
