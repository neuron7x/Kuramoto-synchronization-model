# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioural coverage for ``modules.strategy_scheduler``.

The scheduler is exercised with real inputs; the only clock control is a fixed
``datetime`` subclass injected into ``_calculate_next_run`` so the schedule-type
branches (DAILY past/future, WEEKLY found/fallback, start/end windows) become
deterministic instead of wall-clock dependent.
"""

from __future__ import annotations

import heapq
from datetime import datetime, time, timedelta
from types import SimpleNamespace
from typing import Iterator

import pytest

from modules import strategy_scheduler as ss


def _noop() -> str:
    return "ok"


def _boom() -> None:
    raise RuntimeError("handler failed")


def _once() -> ss.ScheduleConfig:
    return ss.ScheduleConfig(schedule_type=ss.ScheduleType.ONCE)


# ── enums ───────────────────────────────────────────────────────────────────
def test_enum_values() -> None:
    assert ss.ScheduleType.INTERVAL.value == "interval"
    assert ss.TaskStatus.RUNNING.value == "running"
    assert ss.TaskPriority.CRITICAL.value == 4


# ── ScheduledTask.__lt__ ────────────────────────────────────────────────────
def _task(next_run: datetime | None, priority: ss.TaskPriority = ss.TaskPriority.NORMAL) -> ss.ScheduledTask:
    return ss.ScheduledTask(
        task_id="t",
        name="n",
        strategy_name="s",
        handler=_noop,
        schedule=_once(),
        priority=priority,
        next_run=next_run,
    )


def test_lt_self_none_is_not_less() -> None:
    now = datetime(2026, 7, 1, 12, 0, 0)
    assert (_task(None) < _task(now)) is False


def test_lt_other_none_is_less() -> None:
    now = datetime(2026, 7, 1, 12, 0, 0)
    assert (_task(now) < _task(None)) is True


def test_lt_equal_time_breaks_on_priority() -> None:
    now = datetime(2026, 7, 1, 12, 0, 0)
    high = _task(now, ss.TaskPriority.HIGH)
    low = _task(now, ss.TaskPriority.LOW)
    # Higher priority sorts as "less" so heapq pops it first.
    assert (high < low) is True
    assert (low < high) is False


def test_lt_orders_by_time() -> None:
    early = _task(datetime(2026, 7, 1, 12, 0, 0))
    late = _task(datetime(2026, 7, 1, 13, 0, 0))
    assert (early < late) is True


# ── schedule / unschedule ───────────────────────────────────────────────────
def test_schedule_interval_enqueues() -> None:
    sched = ss.StrategyScheduler()
    tid = sched.schedule(
        "n", "strat", _noop,
        ss.ScheduleConfig(schedule_type=ss.ScheduleType.INTERVAL, interval_seconds=60),
    )
    assert tid in sched._tasks
    assert len(sched._queue) == 1


def test_schedule_no_next_run_not_enqueued() -> None:
    sched = ss.StrategyScheduler()
    # INTERVAL without interval_seconds → next_run None → not queued.
    tid = sched.schedule(
        "n", "strat", _noop,
        ss.ScheduleConfig(schedule_type=ss.ScheduleType.INTERVAL),
    )
    assert sched._tasks[tid].next_run is None
    assert len(sched._queue) == 0


def test_schedule_on_event_registers_handler() -> None:
    sched = ss.StrategyScheduler()
    tid = sched.schedule(
        "n", "strat", _noop,
        ss.ScheduleConfig(schedule_type=ss.ScheduleType.ON_EVENT, event_trigger="signal"),
    )
    assert sched._event_handlers["signal"] == [tid]
    assert len(sched._queue) == 0


def test_schedule_custom_timeout_and_metadata() -> None:
    sched = ss.StrategyScheduler(default_timeout=10.0)
    tid = sched.schedule(
        "n", "strat", _noop, _once(),
        timeout_seconds=99.0, metadata={"k": "v"},
        dependencies={"other"},
    )
    task = sched._tasks[tid]
    assert task.timeout_seconds == 99.0
    assert task.metadata == {"k": "v"}
    assert task.dependencies == {"other"}


def test_unschedule_missing_returns_false() -> None:
    assert ss.StrategyScheduler().unschedule("ghost") is False


def test_unschedule_event_task_removes_handler() -> None:
    sched = ss.StrategyScheduler()
    tid = sched.schedule(
        "n", "strat", _noop,
        ss.ScheduleConfig(schedule_type=ss.ScheduleType.ON_EVENT, event_trigger="e"),
    )
    assert sched.unschedule(tid) is True
    assert tid not in sched._tasks
    assert tid not in sched._event_handlers["e"]


def test_unschedule_plain_task() -> None:
    sched = ss.StrategyScheduler()
    tid = sched.schedule("n", "strat", _noop, _once())
    assert sched.unschedule(tid) is True
    assert tid not in sched._tasks


# ── pause / resume ──────────────────────────────────────────────────────────
def test_pause_missing_false() -> None:
    assert ss.StrategyScheduler().pause("ghost") is False


def test_pause_and_resume_cycle() -> None:
    sched = ss.StrategyScheduler()
    tid = sched.schedule(
        "n", "strat", _noop,
        ss.ScheduleConfig(schedule_type=ss.ScheduleType.INTERVAL, interval_seconds=30),
    )
    assert sched.pause(tid) is True
    assert sched._tasks[tid].status == ss.TaskStatus.PAUSED
    assert sched.resume(tid) is True
    assert sched._tasks[tid].status == ss.TaskStatus.PENDING


def test_resume_missing_false() -> None:
    assert ss.StrategyScheduler().resume("ghost") is False


def test_resume_not_paused_false() -> None:
    sched = ss.StrategyScheduler()
    tid = sched.schedule("n", "strat", _noop, _once())
    assert sched.resume(tid) is False


# ── trigger_event / run_now ─────────────────────────────────────────────────
def test_trigger_event_runs_pending_with_payload() -> None:
    sched = ss.StrategyScheduler()
    tid = sched.schedule(
        "n", "strat", _noop,
        ss.ScheduleConfig(schedule_type=ss.ScheduleType.ON_EVENT, event_trigger="e"),
    )
    count = sched.trigger_event("e", payload={"x": 1})
    assert count == 1
    assert sched._tasks[tid].metadata["event_payload"] == {"x": 1}


def test_trigger_event_unknown_zero() -> None:
    assert ss.StrategyScheduler().trigger_event("nope") == 0


def test_trigger_event_skips_non_pending() -> None:
    sched = ss.StrategyScheduler()
    cfg = ss.ScheduleConfig(schedule_type=ss.ScheduleType.ON_EVENT, event_trigger="e")
    tid = sched.schedule("n", "strat", _noop, cfg)
    sched.pause(tid)  # status PAUSED, still registered on the event
    assert sched.trigger_event("e") == 0


def test_run_now_missing_none() -> None:
    assert ss.StrategyScheduler().run_now("ghost") is None


def test_run_now_success() -> None:
    sched = ss.StrategyScheduler()
    tid = sched.schedule("n", "strat", _noop, _once())
    execution = sched.run_now(tid)
    assert execution is not None
    assert execution.status == ss.TaskStatus.COMPLETED
    assert execution.result == "ok"
    assert sched._tasks[tid].run_count == 1


def test_run_now_handler_exception_marks_failed() -> None:
    sched = ss.StrategyScheduler()
    tid = sched.schedule("n", "strat", _boom, _once())
    execution = sched.run_now(tid)
    assert execution is not None
    assert execution.status == ss.TaskStatus.FAILED
    assert execution.error == "handler failed"
    assert sched._tasks[tid].status == ss.TaskStatus.FAILED
    assert sched._tasks[tid].error_count == 1


def test_execute_recurring_reschedules() -> None:
    sched = ss.StrategyScheduler()
    tid = sched.schedule(
        "n", "strat", _noop,
        ss.ScheduleConfig(schedule_type=ss.ScheduleType.INTERVAL, interval_seconds=15),
    )
    sched._queue.clear()
    sched.run_now(tid)
    # Non-ONCE success reschedules into the queue.
    assert any(t.task_id == tid for t in sched._queue)


def test_execute_history_trimmed_to_cap() -> None:
    sched = ss.StrategyScheduler()
    tid = sched.schedule("n", "strat", _noop, _once())
    filler = [
        ss.TaskExecution(execution_id=f"e{i}", task_id="old", started_at=datetime.now())
        for i in range(1000)
    ]
    sched._execution_history = filler
    sched.run_now(tid)
    assert len(sched._execution_history) == 1000
    assert sched._execution_history[-1].task_id == tid


# ── getters ─────────────────────────────────────────────────────────────────
def test_get_task_and_filters() -> None:
    sched = ss.StrategyScheduler()
    a = sched.schedule("a", "alpha", _noop, _once())
    b = sched.schedule("b", "beta", _noop, _once())
    assert sched.get_task(a) is not None
    assert sched.get_task("ghost") is None
    assert {t.task_id for t in sched.get_tasks(strategy_name="alpha")} == {a}
    sched._tasks[b].status = ss.TaskStatus.COMPLETED
    assert {t.task_id for t in sched.get_tasks(status=ss.TaskStatus.COMPLETED)} == {b}
    assert len(sched.get_tasks()) == 2


def test_get_execution_history_filter_and_limit() -> None:
    sched = ss.StrategyScheduler()
    base = datetime(2026, 7, 1, 12, 0, 0)
    sched._execution_history = [
        ss.TaskExecution(execution_id="e1", task_id="A", started_at=base),
        ss.TaskExecution(execution_id="e2", task_id="B", started_at=base + timedelta(seconds=1)),
        ss.TaskExecution(execution_id="e3", task_id="A", started_at=base + timedelta(seconds=2)),
    ]
    only_a = sched.get_execution_history(task_id="A")
    assert [e.execution_id for e in only_a] == ["e3", "e1"]
    assert len(sched.get_execution_history(limit=1)) == 1


def test_get_stats_counts() -> None:
    sched = ss.StrategyScheduler()
    p = sched.schedule("p", "s", _noop, _once())
    c = sched.schedule("c", "s", _noop, _once())
    f = sched.schedule("f", "s", _noop, _once())
    sched._tasks[c].status = ss.TaskStatus.COMPLETED
    sched._tasks[f].status = ss.TaskStatus.FAILED
    sched._execution_history = [
        ss.TaskExecution("e1", p, datetime.now(), status=ss.TaskStatus.COMPLETED),
        ss.TaskExecution("e2", f, datetime.now(), status=ss.TaskStatus.FAILED),
    ]
    stats = sched.get_stats()
    assert stats.total_tasks == 3
    assert stats.pending_tasks == 1
    assert stats.completed_tasks == 1
    assert stats.failed_tasks == 1
    assert stats.successful_executions == 1
    assert stats.failed_executions == 1


def test_summary_na_then_percentage() -> None:
    sched = ss.StrategyScheduler()
    empty = sched.get_summary()
    assert empty["success_rate"] == "N/A"
    tid = sched.schedule(
        "n", "strat", _noop,
        ss.ScheduleConfig(schedule_type=ss.ScheduleType.INTERVAL, interval_seconds=60),
    )
    sched.run_now(tid)
    summary = sched.get_summary()
    assert summary["success_rate"] == "100.0%"
    assert summary["upcoming_tasks"]  # pending task with next_run present
    assert summary["total_executions"] == 1


# ── tick ────────────────────────────────────────────────────────────────────
def test_tick_executes_due_task() -> None:
    sched = ss.StrategyScheduler()
    sched.schedule("n", "strat", _noop, _once())
    executions = sched.tick()
    assert len(executions) == 1
    assert executions[0].status == ss.TaskStatus.COMPLETED


def test_tick_skips_future_task() -> None:
    sched = ss.StrategyScheduler()
    sched.schedule(
        "n", "strat", _noop,
        ss.ScheduleConfig(schedule_type=ss.ScheduleType.INTERVAL, interval_seconds=3600),
    )
    assert sched.tick() == []


def test_tick_respects_max_concurrent_zero() -> None:
    sched = ss.StrategyScheduler(max_concurrent_tasks=0)
    sched.schedule("n", "strat", _noop, _once())
    assert sched.tick() == []


def test_tick_skips_non_pending() -> None:
    sched = ss.StrategyScheduler()
    tid = sched.schedule("n", "strat", _noop, _once())
    sched._tasks[tid].status = ss.TaskStatus.PAUSED
    assert sched.tick() == []


def test_tick_requeues_when_dependency_unmet() -> None:
    sched = ss.StrategyScheduler(enable_dependency_check=True)
    dep = sched.schedule(
        "dep", "s", _noop,
        ss.ScheduleConfig(schedule_type=ss.ScheduleType.ON_EVENT, event_trigger="e"),
    )  # never run → run_count 0
    main = sched.schedule("main", "s", _noop, _once(), dependencies={dep})
    result = sched.tick()
    assert result == []
    requeued = next(t for t in sched._queue if t.task_id == main)
    assert requeued.next_run is not None


# ── _check_dependencies ─────────────────────────────────────────────────────
def _register(sched: ss.StrategyScheduler, task_id: str, status: ss.TaskStatus, runs: int) -> None:
    task = ss.ScheduledTask(
        task_id=task_id, name=task_id, strategy_name="s", handler=_noop,
        schedule=_once(), status=status, run_count=runs,
    )
    sched._tasks[task_id] = task


def test_check_dependencies_variants() -> None:
    sched = ss.StrategyScheduler()
    target = ss.ScheduledTask(
        task_id="tgt", name="t", strategy_name="s", handler=_noop, schedule=_once(),
    )

    target.dependencies = {"ghost"}  # missing → skipped → passes
    assert sched._check_dependencies(target) is True

    _register(sched, "run", ss.TaskStatus.RUNNING, 1)
    target.dependencies = {"run"}
    assert sched._check_dependencies(target) is False

    _register(sched, "fail", ss.TaskStatus.FAILED, 1)
    target.dependencies = {"fail"}
    assert sched._check_dependencies(target) is False

    _register(sched, "never", ss.TaskStatus.PENDING, 0)
    target.dependencies = {"never"}
    assert sched._check_dependencies(target) is False

    _register(sched, "done", ss.TaskStatus.COMPLETED, 3)
    target.dependencies = {"done"}
    assert sched._check_dependencies(target) is True


# ── _calculate_next_run (deterministic clock) ───────────────────────────────
_FIXED = datetime(2026, 7, 1, 12, 0, 0)  # Wednesday


@pytest.fixture()
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # ``_calculate_next_run`` only reaches ``datetime.now`` and ``datetime.combine``;
    # a namespace pinning ``now`` keeps schedule-type branches wall-clock independent.
    frozen = SimpleNamespace(
        now=lambda: _FIXED,
        combine=datetime.combine,
        max=datetime.max,
    )
    monkeypatch.setattr(ss, "datetime", frozen)
    yield


def _calc(cfg: ss.ScheduleConfig) -> datetime | None:
    return ss.StrategyScheduler()._calculate_next_run(cfg)


def test_calc_start_time_in_future(fixed_clock: None) -> None:
    future = _FIXED + timedelta(hours=1)
    cfg = ss.ScheduleConfig(schedule_type=ss.ScheduleType.INTERVAL, start_time=future)
    assert _calc(cfg) == future


def test_calc_end_time_in_past_none(fixed_clock: None) -> None:
    cfg = ss.ScheduleConfig(
        schedule_type=ss.ScheduleType.INTERVAL,
        interval_seconds=10,
        end_time=_FIXED - timedelta(hours=1),
    )
    assert _calc(cfg) is None


def test_calc_once_immediate(fixed_clock: None) -> None:
    assert _calc(ss.ScheduleConfig(schedule_type=ss.ScheduleType.ONCE)) == _FIXED


def test_calc_once_past_start_time(fixed_clock: None) -> None:
    cfg = ss.ScheduleConfig(
        schedule_type=ss.ScheduleType.ONCE, start_time=_FIXED - timedelta(hours=2)
    )
    assert _calc(cfg) == _FIXED


def test_calc_interval(fixed_clock: None) -> None:
    cfg = ss.ScheduleConfig(schedule_type=ss.ScheduleType.INTERVAL, interval_seconds=90)
    assert _calc(cfg) == _FIXED + timedelta(seconds=90)


def test_calc_interval_missing_none(fixed_clock: None) -> None:
    assert _calc(ss.ScheduleConfig(schedule_type=ss.ScheduleType.INTERVAL)) is None


def test_calc_daily_past_rolls_forward(fixed_clock: None) -> None:
    cfg = ss.ScheduleConfig(schedule_type=ss.ScheduleType.DAILY, run_at_time=time(9, 0))
    result = _calc(cfg)
    assert result == datetime.combine((_FIXED + timedelta(days=1)).date(), time(9, 0))


def test_calc_daily_future_same_day(fixed_clock: None) -> None:
    cfg = ss.ScheduleConfig(schedule_type=ss.ScheduleType.DAILY, run_at_time=time(15, 0))
    assert _calc(cfg) == datetime.combine(_FIXED.date(), time(15, 0))


def test_calc_daily_missing_none(fixed_clock: None) -> None:
    assert _calc(ss.ScheduleConfig(schedule_type=ss.ScheduleType.DAILY)) is None


def test_calc_weekly_finds_next_day(fixed_clock: None) -> None:
    cfg = ss.ScheduleConfig(
        schedule_type=ss.ScheduleType.WEEKLY,
        run_at_time=time(15, 0),
        days_of_week={0, 1, 2, 3, 4, 5, 6},
    )
    assert _calc(cfg) == datetime.combine(_FIXED.date(), time(15, 0))


def test_calc_weekly_fallback_plus_seven(fixed_clock: None) -> None:
    cfg = ss.ScheduleConfig(
        schedule_type=ss.ScheduleType.WEEKLY,
        run_at_time=time(9, 0),  # already past today
        days_of_week={_FIXED.weekday()},  # only today qualifies
    )
    assert _calc(cfg) == _FIXED + timedelta(days=7)


def test_calc_weekly_missing_none(fixed_clock: None) -> None:
    cfg = ss.ScheduleConfig(schedule_type=ss.ScheduleType.WEEKLY, days_of_week=set())
    assert _calc(cfg) is None


def test_calc_on_event_none(fixed_clock: None) -> None:
    cfg = ss.ScheduleConfig(schedule_type=ss.ScheduleType.ON_EVENT, event_trigger="e")
    assert _calc(cfg) is None


def test_calc_cron_unhandled_none(fixed_clock: None) -> None:
    cfg = ss.ScheduleConfig(schedule_type=ss.ScheduleType.CRON, cron_expression="* * * * *")
    assert _calc(cfg) is None


def test_heapq_ordering_smoke() -> None:
    heap: list[ss.ScheduledTask] = []
    heapq.heappush(heap, _task(datetime(2026, 7, 1, 13, 0, 0)))
    heapq.heappush(heap, _task(datetime(2026, 7, 1, 12, 0, 0)))
    assert heapq.heappop(heap).next_run == datetime(2026, 7, 1, 12, 0, 0)
