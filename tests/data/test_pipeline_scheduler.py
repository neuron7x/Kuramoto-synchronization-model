"""Tests for the adaptive :class:`PipelineScheduler`."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Callable

import pytest

from src.data.etl.pipeline import PipelineRunConfig, PipelineScheduler


class RecordingPipeline:
    """Lightweight pipeline stub that records scheduler dynamics."""

    def __init__(self, delay: float = 0.01) -> None:
        self.delay = delay
        self.completed: list[str] = []
        self.cancelled = 0
        self.max_concurrency = 0
        self._active = 0
        self._lock = asyncio.Lock()
        self._done_event = asyncio.Event()
        self._expected_total: int | None = None

    def set_expected_total(self, total: int) -> None:
        self._expected_total = total
        if len(self.completed) >= total:
            self._done_event.set()
        else:
            self._done_event.clear()

    async def wait_for_expected(self, timeout: float = 2.0) -> None:
        if self._expected_total is None:
            raise RuntimeError("Expected total must be configured before waiting")
        await asyncio.wait_for(self._done_event.wait(), timeout=timeout)

    async def run(self, config: PipelineRunConfig) -> None:
        try:
            async with self._lock:
                self._active += 1
                self.max_concurrency = max(self.max_concurrency, self._active)
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            async with self._lock:
                self._active -= 1
                self.cancelled += 1
            raise
        else:
            async with self._lock:
                self._active -= 1
                self.completed.append(config.run_id)
                if (
                    self._expected_total is not None
                    and len(self.completed) >= self._expected_total
                ):
                    self._done_event.set()


async def _wait_for(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if condition():
            return
        if loop.time() >= deadline:
            raise AssertionError("Condition not met within timeout")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_scheduler_scales_without_cancellation() -> None:
    pipeline = RecordingPipeline(delay=0.02)
    scheduler = PipelineScheduler(
        pipeline,
        poll_interval=timedelta(milliseconds=10),
        max_workers=4,
    )
    await scheduler.start()

    total_runs = 6
    pipeline.set_expected_total(total_runs)
    for idx in range(total_runs):
        await scheduler.submit(
            PipelineRunConfig(run_id=f"run-{idx}", partition_key=str(idx))
        )

    await pipeline.wait_for_expected()
    await scheduler.shutdown()

    assert pipeline.cancelled == 0
    assert len(pipeline.completed) == total_runs
    assert pipeline.max_concurrency > 1


@pytest.mark.asyncio
async def test_scheduler_downscales_and_recovers() -> None:
    pipeline = RecordingPipeline(delay=0.01)
    scheduler = PipelineScheduler(
        pipeline,
        poll_interval=timedelta(milliseconds=10),
        max_workers=4,
    )
    await scheduler.start()

    first_batch = 3
    pipeline.set_expected_total(first_batch)
    for idx in range(first_batch):
        await scheduler.submit(
            PipelineRunConfig(run_id=f"first-{idx}", partition_key=str(idx))
        )

    await pipeline.wait_for_expected()
    await _wait_for(lambda: len(scheduler._workers) == 0)

    second_batch = 2
    pipeline.set_expected_total(first_batch + second_batch)
    for idx in range(second_batch):
        await scheduler.submit(
            PipelineRunConfig(run_id=f"second-{idx}", partition_key=str(idx))
        )

    await pipeline.wait_for_expected()
    await scheduler.shutdown()

    assert pipeline.cancelled == 0
    assert len(pipeline.completed) == first_batch + second_batch
