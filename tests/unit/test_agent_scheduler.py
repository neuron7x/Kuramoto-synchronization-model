# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the strategy scheduler."""

from __future__ import annotations

import random
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

import pytest

from core.agent.evaluator import EvaluationResult
from core.agent.scheduler import SlaMissedError, StrategyJob, StrategyScheduler
from core.agent.strategy import Strategy


class FakeClock:
    def __init__(self, start: float = 0.0, *, wall_start: datetime | None = None) -> None:
        self._now = float(start)
        self._wall_start = wall_start or datetime(2024, 1, 1, tzinfo=timezone.utc)

    def now(self) -> float:
        return self._now

    def wall_time(self) -> float:
        return (self._wall_start + timedelta(seconds=self._now)).timestamp()

    def advance(self, delta: float) -> None:
        self._now += float(delta)


class DummyEvaluator:
    def __init__(self) -> None:
        self.calls: list[tuple[Sequence[Strategy], Any, bool]] = []

    def evaluate(
        self,
        strategies: Sequence[Strategy],
        data: Any,
        *,
        raise_on_error: bool = False,
    ) -> list[EvaluationResult]:
        self.calls.append((tuple(strategies), data, raise_on_error))
        results: list[EvaluationResult] = []
        for strategy in strategies:
            results.append(EvaluationResult(strategy=strategy, score=1.0, duration=0.0, error=None))
        return results


class SlowEvaluator(DummyEvaluator):
    def __init__(self, clock: FakeClock, duration: float) -> None:
        super().__init__()
        self._clock = clock
        self._duration = duration

    def evaluate(
        self,
        strategies: Sequence[Strategy],
        data: Any,
        *,
        raise_on_error: bool = False,
    ) -> list[EvaluationResult]:
        self._clock.advance(self._duration)
        return super().evaluate(strategies, data, raise_on_error=raise_on_error)


class BlockingEvaluator:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def evaluate(
        self,
        strategies: Sequence[Strategy],
        data: Any,
        *,
        raise_on_error: bool = False,
    ) -> list[EvaluationResult]:
        self.started.set()
        if not self.release.wait(timeout=1.0):  # pragma: no cover - defensive timeout guard
            raise TimeoutError("BlockingEvaluator release was not signalled")
        return [
            EvaluationResult(strategy=strategy, score=1.0, duration=0.0, error=None)
            for strategy in strategies
        ]


def _make_scheduler(clock: FakeClock, evaluator: DummyEvaluator | None = None) -> StrategyScheduler:
    evaluator = evaluator or DummyEvaluator()
    return StrategyScheduler(
        evaluator=evaluator,
        time_source=clock.now,
        wall_time=clock.wall_time,
        sleep=lambda _: None,
        rng=random.Random(42),
        max_backoff=3600.0,
    )


def test_scheduler_executes_due_jobs() -> None:
    clock = FakeClock()
    evaluator = DummyEvaluator()
    scheduler = _make_scheduler(clock, evaluator)

    strategy = Strategy(name="mean_revert", params={"lookback": 20, "threshold": 0.5})
    data_points = [100.0, 101.5, 102.0, 101.0, 100.5]

    job = StrategyJob(
        name="replay",
        strategies=[strategy],
        data_provider=lambda: data_points,
        interval=5.0,
    )
    scheduler.add_job(job)

    assert scheduler.run_pending() == {}

    clock.advance(5.0)
    results = scheduler.run_pending()
    assert "replay" in results
    replay_results = results["replay"]
    assert len(replay_results) == 1
    assert isinstance(replay_results[0], EvaluationResult)
    assert evaluator.calls[0][0][0] is strategy

    status = scheduler.get_status("replay")
    assert status.result_count == 1
    assert status.last_error is None
    assert status.consecutive_failures == 0
    assert status.last_run_at == pytest.approx(clock.now())


def test_scheduler_respects_jitter_and_reschedules() -> None:
    clock = FakeClock()
    scheduler = _make_scheduler(clock)

    strategy = Strategy(name="momentum", params={"lookback": 15, "threshold": 0.3})
    job = StrategyJob(
        name="jittered",
        strategies=[strategy],
        data_provider=lambda: [1.0, 1.1, 1.2, 1.3],
        interval=10.0,
        jitter=2.0,
    )
    scheduler.add_job(job)

    status = scheduler.get_status("jittered")
    first_delay = status.next_run_at - clock.now()
    assert 8.0 <= first_delay <= 12.0

    clock.advance(first_delay)
    scheduler.run_pending()
    next_status = scheduler.get_status("jittered")
    second_delay = next_status.next_run_at - clock.now()
    assert 8.0 <= second_delay <= 12.0


def test_scheduler_applies_backoff_on_failure() -> None:
    clock = FakeClock()
    evaluator = DummyEvaluator()
    scheduler = _make_scheduler(clock, evaluator)

    strategy = Strategy(name="fail", params={"lookback": 10, "threshold": 0.2})

    def failing_data() -> list[float]:
        raise RuntimeError("dataset unavailable")

    job = StrategyJob(
        name="failing",
        strategies=[strategy],
        data_provider=failing_data,
        interval=4.0,
    )
    scheduler.add_job(job, run_immediately=True)

    scheduler.run_pending()
    status = scheduler.get_status("failing")
    assert status.consecutive_failures == 1
    assert isinstance(status.last_error, RuntimeError)
    assert status.result_count == 0
    first_backoff = status.next_run_at - clock.now()
    assert pytest.approx(first_backoff) == 4.0

    clock.advance(first_backoff)
    scheduler.run_pending()
    status = scheduler.get_status("failing")
    assert status.consecutive_failures == 2
    second_backoff = status.next_run_at - clock.now()
    assert pytest.approx(second_backoff) == 8.0


def test_scheduler_invokes_callbacks() -> None:
    clock = FakeClock()
    evaluator = DummyEvaluator()
    scheduler = _make_scheduler(clock, evaluator)

    strategy = Strategy(name="callbacks", params={"lookback": 25, "threshold": 0.4})
    completed: list[Sequence[EvaluationResult]] = []
    errors: list[BaseException] = []

    def on_complete(job: StrategyJob, results: Sequence[EvaluationResult]) -> None:
        completed.append(results)

    def on_error(job: StrategyJob, error: BaseException) -> None:
        errors.append(error)

    data_points = [100.0, 101.0, 99.0, 100.5]

    job = StrategyJob(
        name="success",
        strategies=[strategy],
        data_provider=lambda: data_points,
        interval=2.0,
        on_complete=on_complete,
        on_error=on_error,
    )
    scheduler.add_job(job, run_immediately=True)

    scheduler.run_pending()
    assert completed and isinstance(completed[0][0], EvaluationResult)
    assert not errors

    # Force an error and ensure the error callback is invoked.
    def failing_provider() -> Sequence[float]:
        raise RuntimeError("boom")

    job.data_provider = failing_provider
    clock.advance(2.0)
    scheduler.run_pending()
    assert errors and isinstance(errors[0], RuntimeError)


def test_scheduler_handles_cron_expression() -> None:
    clock = FakeClock()
    evaluator = DummyEvaluator()
    scheduler = _make_scheduler(clock, evaluator)

    strategy = Strategy(name="cron", params={})
    job = StrategyJob(
        name="cron-job",
        strategies=[strategy],
        data_provider=lambda: [1, 2, 3],
        cron="*/5 * * * *",
    )
    scheduler.add_job(job)

    status = scheduler.get_status("cron-job")
    assert status.next_run_at - clock.now() == pytest.approx(300.0)

    clock.advance(300.0)
    results = scheduler.run_pending()
    assert "cron-job" in results

    next_status = scheduler.get_status("cron-job")
    assert next_status.next_run_at - clock.now() == pytest.approx(300.0)


def test_scheduler_runs_event_driven_jobs_once_per_trigger() -> None:
    clock = FakeClock()
    scheduler = _make_scheduler(clock)

    strategy = Strategy(name="event", params={})
    job = StrategyJob(
        name="event-job",
        strategies=[strategy],
        data_provider=lambda: [42],
        event_triggers=("tick",),
    )
    scheduler.add_job(job)

    scheduler.trigger_event("tick")
    first = scheduler.run_pending()
    assert "event-job" in first

    status = scheduler.get_status("event-job")
    assert status.pending_events == 0

    scheduler.trigger_event("tick")
    scheduler.trigger_event("tick")
    # Each trigger is processed serially across consecutive run cycles.
    second = scheduler.run_pending()
    assert "event-job" in second
    third = scheduler.run_pending()
    assert "event-job" in third


def test_scheduler_enforces_dependencies() -> None:
    clock = FakeClock()
    scheduler = _make_scheduler(clock)

    upstream_strategy = Strategy(name="root", params={})
    downstream_strategy = Strategy(name="child", params={})

    upstream = StrategyJob(
        name="upstream",
        strategies=[upstream_strategy],
        data_provider=lambda: [1],
        interval=1.0,
    )
    scheduler.add_job(upstream, run_immediately=True)

    downstream = StrategyJob(
        name="downstream",
        strategies=[downstream_strategy],
        data_provider=lambda: [2],
        interval=1.0,
        depends_on=("upstream",),
    )
    scheduler.add_job(downstream, run_immediately=True)

    results = scheduler.run_pending()
    assert "upstream" in results
    assert "downstream" not in results

    clock.advance(1.0)
    next_results = scheduler.run_pending()
    assert "downstream" not in next_results

    follow_up = scheduler.run_pending()
    assert "downstream" in follow_up


def test_scheduler_flags_sla_violations() -> None:
    clock = FakeClock()
    evaluator = SlowEvaluator(clock, duration=5.0)
    scheduler = _make_scheduler(clock, evaluator)

    strategy = Strategy(name="sla", params={})
    job = StrategyJob(
        name="sla-job",
        strategies=[strategy],
        data_provider=lambda: [1],
        interval=2.0,
        sla_seconds=1.0,
    )
    scheduler.add_job(job, run_immediately=True)

    scheduler.run_pending()
    status = scheduler.get_status("sla-job")
    assert isinstance(status.last_error, SlaMissedError)
    assert status.consecutive_failures == 1


def test_scheduler_honors_delayed_start() -> None:
    clock = FakeClock()
    scheduler = _make_scheduler(clock)

    strategy = Strategy(name="delayed", params={})
    job = StrategyJob(
        name="delayed-job",
        strategies=[strategy],
        data_provider=lambda: [1],
        interval=2.0,
        start_at=timedelta(seconds=5),
    )
    scheduler.add_job(job)

    status = scheduler.get_status("delayed-job")
    assert status.next_run_at - clock.now() == pytest.approx(5.0)

    clock.advance(4.0)
    assert scheduler.run_pending() == {}

    clock.advance(1.0)
    results = scheduler.run_pending()
    assert "delayed-job" in results


def test_scheduler_stop_waits_for_inflight_jobs() -> None:
    clock = FakeClock()
    evaluator = BlockingEvaluator()
    scheduler = StrategyScheduler(
        evaluator=evaluator,
        time_source=clock.now,
        wall_time=clock.wall_time,
        sleep=lambda _: None,
        rng=random.Random(7),
    )

    strategy = Strategy(name="blocking", params={})
    job = StrategyJob(
        name="blocking-job",
        strategies=[strategy],
        data_provider=lambda: [1],
        interval=10.0,
    )
    scheduler.add_job(job, run_immediately=True)

    scheduler.start()
    assert evaluator.started.wait(timeout=1.0)

    stop_thread = threading.Thread(target=scheduler.stop, kwargs={"wait": True})
    stop_thread.start()
    assert not stop_thread.join(timeout=0.05)

    evaluator.release.set()
    stop_thread.join(timeout=1.0)
    assert not stop_thread.is_alive()
