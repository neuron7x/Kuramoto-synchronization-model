# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import asyncio

import pytest

from application.api.idempotency import (
    IdempotencyCache,
    IdempotencyConflictError,
)


@pytest.mark.asyncio
async def test_set_rejects_conflicting_payloads() -> None:
    cache = IdempotencyCache(ttl_seconds=60)

    await cache.set(
        key="key-123",
        payload_hash="hash-1",
        body={"result": "ok"},
        status_code=200,
        headers={"ETag": "abc"},
    )

    with pytest.raises(IdempotencyConflictError):
        await cache.set(
            key="key-123",
            payload_hash="hash-2",
            body={"result": "different"},
            status_code=200,
            headers={},
        )


@pytest.mark.asyncio
async def test_concurrent_conflicts_are_rejected() -> None:
    cache = IdempotencyCache(ttl_seconds=60)
    ready = asyncio.Event()

    async def writer(hash_value: str) -> None:
        await ready.wait()
        await cache.set(
            key="shared",
            payload_hash=hash_value,
            body={"hash": hash_value},
            status_code=200,
            headers={},
        )

    first = asyncio.create_task(writer("hash-a"))
    second = asyncio.create_task(writer("hash-b"))

    # Ensure both tasks are waiting on the barrier before releasing them.
    await asyncio.sleep(0)
    ready.set()

    results = await asyncio.gather(first, second, return_exceptions=True)

    # Exactly one branch should raise a conflict and the cache keeps the first record.
    conflict_errors = [result for result in results if isinstance(result, Exception)]
    assert len(conflict_errors) == 1
    assert isinstance(conflict_errors[0], IdempotencyConflictError)

    record = await cache.get("shared")
    assert record is not None
    assert record.payload_hash in {"hash-a", "hash-b"}
