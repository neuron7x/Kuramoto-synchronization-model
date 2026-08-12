# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic concurrency tests for the runtime concurrency matrix.

These cover the failure classes that don't already have a dedicated deterministic
test elsewhere (risk serialisation, realtime cache CAS and the kafka orphan test
are bound to their existing homes by ``artifacts/concurrency/concurrency_matrix.json``):

* kafka ``stop()`` cancels every tracked consumer task (missed cancellation);
* the strategy scheduler issues unique ids under concurrent registration (lost
  update on the id counter → double submit);
* the sliding-window rate limiter counts every concurrent hit (bypass);
* a db session is closed even when its body raises under concurrency (timeout /
  exception path leaks a connection).

Each is deterministic (barrier/gather-synchronised with an exact post-condition),
not a probabilistic stress loop.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine

from application.api.rate_limit import InMemorySlidingWindowBackend
from core.messaging.event_bus import EventBusBackend, EventBusConfig, KafkaEventBus
from libs.db.session import SessionManager
from modules.strategy_scheduler import (
    ScheduleConfig,
    ScheduleType,
    StrategyScheduler,
)


@pytest.mark.asyncio
async def test_kafka_stop_cancels_every_consumer_task() -> None:
    bus = KafkaEventBus(
        EventBusConfig(backend=EventBusBackend.KAFKA, bootstrap_servers="localhost:9092")
    )

    async def _forever() -> None:
        await asyncio.sleep(3600)

    task_a = asyncio.create_task(_forever())
    task_b = asyncio.create_task(_forever())
    bus._consumer_tasks = {"topic-a": [task_a], "topic-b": [task_b]}
    bus._producer = None

    await bus.stop()

    assert task_a.cancelled() and task_b.cancelled()
    assert bus._consumer_tasks == {}  # no orphaned handle left behind


def test_strategy_scheduler_concurrent_registration_yields_unique_ids() -> None:
    scheduler = StrategyScheduler()
    count = 64
    barrier = threading.Barrier(count)
    ids: list[str] = []
    lock = threading.Lock()

    def _register(index: int) -> None:
        barrier.wait()
        task_id = scheduler.schedule(
            name=f"job-{index}",
            strategy_name="alpha",
            handler=lambda: None,
            schedule=ScheduleConfig(schedule_type=ScheduleType.INTERVAL, interval_seconds=60.0),
        )
        with lock:
            ids.append(task_id)

    # max_workers must cover every barrier party, else the pool starves the
    # barrier and deadlocks.
    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(_register, i) for i in range(count)]
    for future in futures:
        future.result()

    # A lost increment on the id counter would collide two ids and drop a task.
    assert len(ids) == count
    assert len(set(ids)) == count


@pytest.mark.asyncio
async def test_rate_limiter_counts_every_concurrent_hit() -> None:
    backend = InMemorySlidingWindowBackend()
    count = 50

    async def _hit() -> int:
        return await backend.hit("client-1", limit=10_000, window_seconds=60.0)

    results = await asyncio.gather(*[_hit() for _ in range(count)])

    # Every hit must be counted exactly once: the returned counts are 1..N.
    assert sorted(results) == list(range(1, count + 1))


class _SpySession:
    """Records the session() lifecycle so we can prove close() always runs."""

    def __init__(self) -> None:
        self.closed = False
        self.rolled_back = False

    def commit(self) -> None:  # pragma: no cover - exception path never commits
        raise AssertionError("commit must not run when the body raises")

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_db_session_closed_on_exception_under_concurrency() -> None:
    engine = create_engine("sqlite://")
    manager = SessionManager(writer_engine=engine, owns_engines=True)
    count = 16
    barrier = threading.Barrier(count)
    spies: list[_SpySession] = []
    lock = threading.Lock()

    def _spy_factory() -> _SpySession:
        spy = _SpySession()
        with lock:
            spies.append(spy)
        return spy

    # Route session() through the spy factory (default writer path).
    setattr(manager, "_select_factory", lambda *, read_only=False: _spy_factory)

    def _use_and_raise(_: int) -> None:
        barrier.wait()
        with pytest.raises(ValueError):
            with manager.session():
                raise ValueError("boom")

    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(_use_and_raise, i) for i in range(count)]
    for future in futures:
        future.result()

    assert len(spies) == count
    # The finally: block must close every session, and the except: must roll back.
    for spy in spies:
        assert spy.closed is True
        assert spy.rolled_back is True
