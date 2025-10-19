from __future__ import annotations

from typing import Callable

import pytest

from core.messaging import idempotency
from core.messaging.idempotency import InMemoryEventIdempotencyStore


@pytest.fixture()
def clock(monkeypatch: pytest.MonkeyPatch) -> Callable[[float], None]:
    current_time = 1_000.0

    def get_time() -> float:
        return current_time

    def set_time(value: float) -> None:
        nonlocal current_time
        current_time = value

    monkeypatch.setattr(idempotency.time, "time", get_time)
    return set_time


def test_double_mark_preserves_latest_timestamp(clock: Callable[[float], None]) -> None:
    store = InMemoryEventIdempotencyStore(ttl_seconds=30)

    store.mark_processed("evt-1")
    clock(1_005.0)
    store.mark_processed("evt-1")

    # Advance beyond the original timestamp while still within the refreshed TTL.
    clock(1_032.0)
    store.purge()

    assert store.was_processed("evt-1") is True


def test_purge_respects_zero_ttl_override(clock: Callable[[float], None]) -> None:
    store = InMemoryEventIdempotencyStore(ttl_seconds=60)

    store.mark_processed("evt-2")
    clock(1_001.0)

    store.purge(ttl_seconds=0)

    assert store.was_processed("evt-2") is False
