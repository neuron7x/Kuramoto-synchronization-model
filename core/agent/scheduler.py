# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Deterministic scheduler that periodically evaluates trading strategies."""
from __future__ import annotations

import logging
import math
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from secrets import SystemRandom
from typing import Any, Callable, Dict, Iterable, Sequence

from .evaluator import EvaluationResult, StrategyBatchEvaluator
from .strategy import Strategy

LOGGER = logging.getLogger(__name__)


StrategyFactory = Callable[[], Sequence[Strategy]]
DatasetProvider = Callable[[], Any]
CompletionCallback = Callable[["StrategyJob", Sequence[EvaluationResult]], None]
ErrorCallback = Callable[["StrategyJob", BaseException], None]


class SlaMissedError(RuntimeError):
    """Raised when a job exceeds its configured SLA."""

    def __init__(self, job_name: str, duration: float, sla: float) -> None:
        super().__init__(f"Job '{job_name}' exceeded SLA: {duration:.2f}s > {sla:.2f}s")
        self.job_name = job_name
        self.duration = duration
        self.sla = sla


class CronExpression:
    """Minimal cron expression parser supporting 5-field schedules."""

    _FIELD_BOUNDS = {
        "minute": (0, 59),
        "hour": (0, 23),
        "day": (1, 31),
        "month": (1, 12),
        "weekday": (0, 6),
    }

    _MONTH_ALIASES = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }

    _WEEKDAY_ALIASES = {
        "sun": 0,
        "mon": 1,
        "tue": 2,
        "wed": 3,
        "thu": 4,
        "fri": 5,
        "sat": 6,
    }

    def __init__(self, expression: str) -> None:
        fields = expression.split()
        if len(fields) != 5:
            raise ValueError("Cron expression must contain exactly five fields")

        minute, hour, day, month, weekday = fields
        self.minutes = self._parse_field(minute, "minute")
        self.hours = self._parse_field(hour, "hour")
        self.days = self._parse_field(day, "day")
        self.months = self._parse_field(month, "month", aliases=self._MONTH_ALIASES)
        self.weekdays = self._parse_field(
            weekday, "weekday", aliases=self._WEEKDAY_ALIASES, sunday_alias=7
        )

    @staticmethod
    def _expand_alias(token: str, aliases: dict[str, int] | None) -> str:
        if aliases is None:
            return token
        lower = token.lower()
        if lower in aliases:
            return str(aliases[lower])
        return token

    def _parse_field(
        self,
        value: str,
        field: str,
        *,
        aliases: dict[str, int] | None = None,
        sunday_alias: int | None = None,
    ) -> frozenset[int]:
        min_value, max_value = self._FIELD_BOUNDS[field]
        tokens = value.split(",")
        results: set[int] = set()
        for token in tokens:
            token = token.strip()
            if token in {"*", "?"}:
                results.update(range(min_value, max_value + 1))
                continue
            if not token:
                raise ValueError(f"Empty token in cron field '{field}'")

            step = 1
            if "/" in token:
                base, step_token = token.split("/", 1)
                if not step_token:
                    raise ValueError(f"Invalid step syntax in cron field '{field}'")
                step = int(self._expand_alias(step_token, aliases))
                if step <= 0:
                    raise ValueError(f"Cron field '{field}' step must be positive")
            else:
                base = token

            base = self._expand_alias(base, aliases)

            if base == "*":
                start = min_value
                end = max_value
            elif "-" in base:
                start_token, end_token = base.split("-", 1)
                start = int(self._expand_alias(start_token, aliases))
                end = int(self._expand_alias(end_token, aliases))
                if start > end:
                    raise ValueError(f"Invalid range '{base}' in cron field '{field}'")
            else:
                start = int(base)
                end = start

            for item in range(start, end + 1, step):
                normalized = item
                if (
                    field == "weekday"
                    and sunday_alias is not None
                    and item == sunday_alias
                ):
                    normalized = 0
                if normalized < min_value or normalized > max_value:
                    raise ValueError(f"Cron field '{field}' value {item} out of range")
                results.add(normalized)

        return frozenset(results)

    def next_after(self, moment: datetime) -> datetime:
        """Return the next datetime strictly after ``moment`` matching the schedule."""

        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        candidate = (moment + timedelta(minutes=1)).replace(second=0, microsecond=0)
        upper_bound = candidate + timedelta(days=366)

        while candidate <= upper_bound:
            if candidate.month not in self.months:
                candidate += self._jump_month(candidate)
                continue

            dom_match = candidate.day in self.days
            dow = candidate.weekday()
            dow_match = dow in self.weekdays

            if candidate.hour not in self.hours or candidate.minute not in self.minutes:
                candidate += timedelta(minutes=1)
                continue

            all_days = len(self.days) == 31
            all_weekdays = len(self.weekdays) == 7

            day_matches: bool
            if all_days and all_weekdays:
                day_matches = True
            elif all_days:
                day_matches = dow_match
            elif all_weekdays:
                day_matches = dom_match
            else:
                day_matches = dom_match or dow_match

            if day_matches:
                return candidate

            candidate += timedelta(minutes=1)

        raise ValueError("Cron expression did not produce a match within one year")

    @staticmethod
    def _jump_month(moment: datetime) -> timedelta:
        """Return the delta required to advance ``moment`` to the next month boundary."""

        year = moment.year + (1 if moment.month == 12 else 0)
        month = 1 if moment.month == 12 else moment.month + 1
        next_month = datetime(year=year, month=month, day=1, tzinfo=moment.tzinfo)
        delta = next_month - moment.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        return delta if delta > timedelta(0) else timedelta(days=1)


@dataclass(slots=True)
class StrategyJob:
    """Configuration for a single scheduled strategy evaluation."""

    name: str
    strategies: Sequence[Strategy] | StrategyFactory
    data_provider: Any | DatasetProvider
    interval: float | None = None
    jitter: float = 0.0
    cron: str | CronExpression | None = None
    event_triggers: Sequence[str] = ()
    depends_on: Sequence[str] = ()
    sla_seconds: float | None = None
    start_at: float | datetime | timedelta | None = None
    raise_on_error: bool = False
    enabled: bool = True
    on_complete: CompletionCallback | None = None
    on_error: ErrorCallback | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("StrategyJob.name must be a non-empty string")
        if self.interval is None and self.cron is None and not self.event_triggers:
            raise ValueError(
                "StrategyJob must define an interval, cron expression, or event trigger"
            )
        if self.interval is not None and self.interval <= 0:
            raise ValueError("StrategyJob.interval must be positive when provided")
        if self.jitter < 0:
            raise ValueError("StrategyJob.jitter must be non-negative")
        if self.jitter and self.interval is None:
            raise ValueError("Jitter can only be used with interval-based jobs")
        if self.sla_seconds is not None and self.sla_seconds <= 0:
            raise ValueError("sla_seconds must be positive when provided")
        if not callable(self.strategies):
            if not isinstance(self.strategies, Sequence):
                raise TypeError(
                    "StrategyJob.strategies must be a sequence or callable returning a sequence"
                )
            if isinstance(self.strategies, (str, bytes)):
                raise TypeError("StrategyJob.strategies cannot be a string")
            strategies = list(self.strategies)
            if not strategies:
                raise ValueError("StrategyJob must include at least one strategy")
            for strategy in strategies:
                if not isinstance(strategy, Strategy):
                    raise TypeError(
                        "StrategyJob.strategies must contain Strategy instances"
                    )
            object.__setattr__(self, "strategies", tuple(strategies))
        if not callable(self.data_provider):
            # Allow static payloads (e.g., DataFrame, ndarray, or None).
            object.__setattr__(self, "data_provider", self.data_provider)

        if isinstance(self.cron, str):
            object.__setattr__(self, "cron", CronExpression(self.cron))
        elif self.cron is not None and not isinstance(self.cron, CronExpression):
            raise TypeError("cron must be a string or CronExpression instance")

        if self.event_triggers:
            triggers = tuple(self._validate_names(self.event_triggers, "event"))
            object.__setattr__(self, "event_triggers", triggers)
        else:
            object.__setattr__(self, "event_triggers", tuple())

        if self.depends_on:
            dependencies = tuple(self._validate_names(self.depends_on, "dependency"))
            if self.name in dependencies:
                raise ValueError("A job cannot depend on itself")
            object.__setattr__(self, "depends_on", dependencies)
        else:
            object.__setattr__(self, "depends_on", tuple())

        if self.start_at is not None and not isinstance(
            self.start_at, (int, float, datetime, timedelta)
        ):
            raise TypeError("start_at must be a float, datetime, or timedelta")

    @staticmethod
    def _validate_names(values: Iterable[str], kind: str) -> Iterable[str]:
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{kind.title()} names must be non-empty strings")
            normalized = value.strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            yield normalized

    def resolve_strategies(self) -> Sequence[Strategy]:
        """Return strategies to evaluate for this job."""

        strategies: Sequence[Strategy]
        if callable(self.strategies):
            strategies = list(self.strategies())
        else:
            strategies = list(self.strategies)
        if not strategies:
            raise ValueError(
                f"Strategy job '{self.name}' did not produce any strategies"
            )
        for strategy in strategies:
            if not isinstance(strategy, Strategy):
                raise TypeError("Strategy factories must return Strategy instances")
        return strategies

    def resolve_dataset(self) -> Any:
        """Return the dataset to pass to the evaluator."""

        if callable(self.data_provider):
            return self.data_provider()
        return self.data_provider


@dataclass(slots=True)
class StrategyJobStatus:
    """Immutable snapshot of a scheduled job."""

    name: str
    enabled: bool
    next_run_at: float
    last_run_at: float | None
    consecutive_failures: int
    in_flight: bool
    last_error: BaseException | None
    result_count: int
    pending_events: int
    depends_on: tuple[str, ...]
    waiting_on: tuple[str, ...]
    sla_deadline_at: float | None


@dataclass(slots=True)
class _JobState:
    job: StrategyJob
    next_run: float = float("inf")
    last_run: float | None = None
    last_results: tuple[EvaluationResult, ...] | None = None
    last_error: BaseException | None = None
    consecutive_failures: int = 0
    in_flight: bool = False
    start_at: float | None = None
    next_interval_run: float | None = None
    next_cron_run: float | None = None
    next_event_run: float | None = None
    pending_events: int = 0
    event_consumed: bool = False
    sla_deadline: float | None = None

    def update_next_run(self) -> None:
        candidates = [
            value
            for value in (
                self.next_interval_run,
                self.next_cron_run,
                self.next_event_run,
            )
            if value is not None
        ]
        self.next_run = min(candidates) if candidates else float("inf")


class StrategyScheduler:
    """Coordinate periodic strategy evaluations."""

    def __init__(
        self,
        *,
        evaluator: StrategyBatchEvaluator | None = None,
        time_source: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        rng: SystemRandom | None = None,
        wall_time: Callable[[], float] | None = None,
        max_backoff: float = 900.0,
        max_sleep: float = 5.0,
        idle_sleep: float = 0.5,
    ) -> None:
        if max_backoff <= 0:
            raise ValueError("max_backoff must be positive")
        if max_sleep <= 0:
            raise ValueError("max_sleep must be positive")
        if idle_sleep <= 0:
            raise ValueError("idle_sleep must be positive")

        self._evaluator = evaluator or StrategyBatchEvaluator()
        self._time = time_source or time.monotonic
        self._sleep = sleep or time.sleep
        self._wall_clock = wall_time or time.time
        self._rng = rng or SystemRandom()
        self._max_backoff = float(max_backoff)
        self._max_sleep = float(max_sleep)
        self._idle_sleep = float(idle_sleep)
        self._jobs: Dict[str, _JobState] = {}
        self._dependents: Dict[str, set[str]] = defaultdict(set)
        self._event_listeners: Dict[str, set[str]] = defaultdict(set)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._accepting_jobs = True
        self._clock_offset = float(self._wall_clock()) - float(self._time())

    # ------------------------------------------------------------------
    # Registration & lifecycle management
    def add_job(self, job: StrategyJob, *, run_immediately: bool = False) -> None:
        """Register ``job`` with the scheduler."""

        with self._lock:
            if job.name in self._jobs:
                raise ValueError(f"Job '{job.name}' is already registered")
            for dependency in job.depends_on:
                if dependency not in self._jobs:
                    raise ValueError(
                        f"Unknown dependency '{dependency}' for job '{job.name}'"
                    )

            now = self._time()
            state = _JobState(job=job)
            state.start_at = self._resolve_start(job.start_at, now)
            self._schedule_interval(state, base=now)
            self._schedule_cron(state, after=self._wall_datetime())
            if run_immediately:
                self._enqueue_event(state, now=now)
            state.update_next_run()

            self._jobs[job.name] = state
            for dependency in job.depends_on:
                self._dependents[dependency].add(job.name)
            for event in job.event_triggers:
                self._event_listeners[event].add(job.name)

    def remove_job(self, name: str) -> None:
        """Remove ``name`` from the scheduler."""

        with self._lock:
            state = self._jobs.get(name)
            if state is None:
                raise KeyError(name)
            dependents = self._dependents.get(name)
            if dependents:
                raise ValueError(
                    f"Cannot remove job '{name}' because dependents {sorted(dependents)} still reference it"
                )

            del self._jobs[name]
            for dependency in state.job.depends_on:
                listeners = self._dependents.get(dependency)
                if listeners is not None:
                    listeners.discard(state.job.name)
                    if not listeners:
                        del self._dependents[dependency]
            for event in state.job.event_triggers:
                listeners = self._event_listeners.get(event)
                if listeners is not None:
                    listeners.discard(state.job.name)
                    if not listeners:
                        del self._event_listeners[event]

    def pause_job(self, name: str) -> None:
        """Temporarily disable a job without removing it."""

        with self._lock:
            state = self._jobs.get(name)
            if state is None:
                raise KeyError(name)
            state.job.enabled = False

    def resume_job(self, name: str, *, run_immediately: bool = False) -> None:
        """Re-enable a paused job."""

        with self._lock:
            state = self._jobs.get(name)
            if state is None:
                raise KeyError(name)
            state.job.enabled = True
            now = self._time()
            self._schedule_interval(state, base=now)
            self._schedule_cron(state, after=self._wall_datetime())
            if run_immediately:
                self._enqueue_event(state, now=now)
            state.update_next_run()

    def trigger_event(self, name: str) -> None:
        """Signal ``name`` to event-driven jobs."""

        now = self._time()
        with self._lock:
            listeners = list(self._event_listeners.get(name, ()))
            for job_name in listeners:
                state = self._jobs.get(job_name)
                if state is None or not state.job.enabled:
                    continue
                self._enqueue_event(state, now=now)
                state.update_next_run()

    # ------------------------------------------------------------------
    # Execution
    def run_pending(self) -> Dict[str, list[EvaluationResult]]:
        """Execute all jobs whose schedule has elapsed."""

        now = self._time()
        due_entries: list[tuple[float, _JobState]] = []

        with self._lock:
            for state in self._jobs.values():
                if not state.job.enabled or state.in_flight or not self._accepting_jobs:
                    continue
                if state.next_run > now:
                    continue
                if not self._dependencies_satisfied(state):
                    continue

                due_time = state.next_run
                state.in_flight = True
                state.sla_deadline = (
                    now + state.job.sla_seconds
                    if state.job.sla_seconds is not None
                    else None
                )
                if (
                    state.pending_events > 0
                    and state.next_event_run is not None
                    and state.next_event_run <= now
                ):
                    state.event_consumed = True
                    state.next_event_run = None
                else:
                    state.event_consumed = False
                state.update_next_run()
                due_entries.append((due_time, state))

        results: Dict[str, list[EvaluationResult]] = {}
        for _, state in sorted(due_entries, key=lambda item: item[0]):
            outcome = self._execute_job(state)
            if outcome is not None:
                results[state.job.name] = list(outcome)
        return results

    def start(self, *, daemon: bool = True) -> None:
        """Start the background scheduling loop."""

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("StrategyScheduler already running")
            self._stop_event.clear()
            self._accepting_jobs = True
            self._thread = threading.Thread(
                target=self._run_loop, name="strategy-scheduler", daemon=daemon
            )
            self._thread.start()

    def stop(self, *, timeout: float | None = None, wait: bool = True) -> None:
        """Stop the background scheduling loop."""

        self._stop_event.set()
        with self._lock:
            self._accepting_jobs = False
            thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        if wait:
            deadline = None if timeout is None else self._time() + timeout
            self._wait_for_inflight(deadline=deadline)
        with self._lock:
            self._thread = None

    # ------------------------------------------------------------------
    # Introspection helpers
    def list_jobs(self) -> list[StrategyJobStatus]:
        """Return snapshots for all registered jobs."""

        with self._lock:
            return [self._snapshot(state) for state in self._jobs.values()]

    def get_status(self, name: str) -> StrategyJobStatus:
        """Return a snapshot for ``name``."""

        with self._lock:
            state = self._jobs.get(name)
            if state is None:
                raise KeyError(name)
            return self._snapshot(state)

    def get_last_results(self, name: str) -> tuple[EvaluationResult, ...] | None:
        """Return the most recent evaluation results for ``name``."""

        with self._lock:
            state = self._jobs.get(name)
            if state is None:
                raise KeyError(name)
            if state.last_results is None:
                return None
            return tuple(state.last_results)

    # ------------------------------------------------------------------
    # Internal helpers
    def _snapshot(self, state: _JobState) -> StrategyJobStatus:
        result_count = 0 if state.last_results is None else len(state.last_results)
        waiting_on = self._dependencies_blockers(state)
        return StrategyJobStatus(
            name=state.job.name,
            enabled=state.job.enabled,
            next_run_at=state.next_run,
            last_run_at=state.last_run,
            consecutive_failures=state.consecutive_failures,
            in_flight=state.in_flight,
            last_error=state.last_error,
            result_count=result_count,
            pending_events=state.pending_events,
            depends_on=state.job.depends_on,
            waiting_on=waiting_on,
            sla_deadline_at=state.sla_deadline,
        )

    def _execute_job(self, state: _JobState) -> tuple[EvaluationResult, ...] | None:
        job = state.job
        started_at = self._time()
        try:
            strategies = job.resolve_strategies()
        except Exception as exc:  # pragma: no cover - defensive path
            self._handle_failure(state, exc, started_at=started_at)
            return None

        try:
            dataset = job.resolve_dataset()
        except Exception as exc:
            self._handle_failure(state, exc, started_at=started_at)
            return None

        try:
            evaluations = tuple(
                self._evaluator.evaluate(
                    strategies, dataset, raise_on_error=job.raise_on_error
                )
            )
        except Exception as exc:
            self._handle_failure(state, exc, started_at=started_at)
            return None

        duration = self._time() - started_at
        if job.sla_seconds is not None and duration > job.sla_seconds:
            self._handle_failure(
                state,
                SlaMissedError(job.name, duration, job.sla_seconds),
                started_at=started_at,
                duration=duration,
            )
            return None

        self._handle_success(
            state, evaluations, started_at=started_at, duration=duration
        )
        return evaluations

    def _handle_success(
        self,
        state: _JobState,
        results: tuple[EvaluationResult, ...],
        *,
        started_at: float,
        duration: float,
    ) -> None:
        completed_at = started_at + max(duration, 0.0)
        job = state.job

        with self._lock:
            state.last_run = completed_at
            state.last_results = results
            state.last_error = None
            state.consecutive_failures = 0
            state.in_flight = False
            state.sla_deadline = None
            self._schedule_interval(state, base=completed_at)
            self._schedule_cron(state, after=self._wall_datetime())
            self._finalize_event_consumption(
                state, completed_at=completed_at, success=True
            )
            state.update_next_run()

        if job.on_complete is not None:
            try:
                job.on_complete(job, results)
            except Exception:  # pragma: no cover - defensive callback guard
                LOGGER.exception(
                    "Strategy job completion handler failed", extra={"job": job.name}
                )

    def _handle_failure(
        self,
        state: _JobState,
        error: BaseException,
        *,
        started_at: float | None = None,
        duration: float | None = None,
    ) -> None:
        finished_at = self._time()
        if started_at is None:
            started_at = finished_at
        job = state.job

        with self._lock:
            state.last_run = finished_at
            state.last_results = None
            state.last_error = error
            state.consecutive_failures += 1
            state.in_flight = False
            state.sla_deadline = None
            backoff = self._compute_backoff(state)
            interval_override = backoff if state.job.interval is not None else None
            self._schedule_interval(
                state,
                base=finished_at,
                interval_override=interval_override,
            )
            self._schedule_cron(state, after=self._wall_datetime())
            self._finalize_event_consumption(
                state,
                completed_at=finished_at,
                success=False,
                retry_delay=backoff,
            )
            state.update_next_run()

        if job.on_error is not None:
            try:
                job.on_error(job, error)
            except Exception:  # pragma: no cover - defensive callback guard
                LOGGER.exception(
                    "Strategy job error handler failed", extra={"job": job.name}
                )
        else:
            LOGGER.warning("Strategy job '%s' failed", job.name, exc_info=error)

    def _compute_backoff(self, state: _JobState) -> float:
        base = (
            state.job.interval if state.job.interval is not None else self._idle_sleep
        )
        exponent = max(state.consecutive_failures - 1, 0)
        return min(base * (2**exponent), self._max_backoff)

    def _schedule_interval(
        self,
        state: _JobState,
        *,
        base: float,
        interval_override: float | None = None,
    ) -> None:
        interval = (
            state.job.interval if interval_override is None else interval_override
        )
        if interval is None:
            state.next_interval_run = None
            return
        delay = max(0.0, interval)
        if state.job.jitter:
            delay = max(
                0.0, delay + self._rng.uniform(-state.job.jitter, state.job.jitter)
            )
        next_time = base + delay
        if state.start_at is not None:
            next_time = max(next_time, state.start_at)
        state.next_interval_run = next_time

    def _schedule_cron(
        self, state: _JobState, *, after: datetime | None = None
    ) -> None:
        cron = state.job.cron
        if cron is None:
            state.next_cron_run = None
            return
        reference = after or self._wall_datetime()
        self._refresh_clock_offset()
        next_wall = cron.next_after(reference)
        next_time = self._monotonic_from_wall(next_wall.timestamp())
        if state.start_at is not None:
            next_time = max(next_time, state.start_at)
        state.next_cron_run = next_time

    def _enqueue_event(self, state: _JobState, *, now: float) -> None:
        state.pending_events += 1
        target = now
        if state.start_at is not None:
            target = max(target, state.start_at)
        if state.next_event_run is None or target < state.next_event_run:
            state.next_event_run = target

    def _finalize_event_consumption(
        self,
        state: _JobState,
        *,
        completed_at: float,
        success: bool,
        retry_delay: float | None = None,
    ) -> None:
        if not state.event_consumed:
            return
        if success:
            if state.pending_events > 0:
                state.pending_events -= 1
            if state.pending_events > 0:
                next_time = max(completed_at, state.start_at or completed_at)
                state.next_event_run = next_time
            else:
                state.next_event_run = None
        else:
            delay = max(0.0, retry_delay or 0.0)
            next_time = completed_at + delay
            if state.start_at is not None:
                next_time = max(next_time, state.start_at)
            state.next_event_run = next_time
        state.event_consumed = False

    def _resolve_start(
        self, value: float | datetime | timedelta | None, now: float
    ) -> float | None:
        if value is None:
            return None
        if isinstance(value, timedelta):
            target = now + value.total_seconds()
        elif isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            self._refresh_clock_offset()
            target = self._monotonic_from_wall(value.timestamp())
        else:
            target = float(value)
            if not math.isfinite(target):
                raise ValueError("start_at must be finite")
        return max(now, target)

    def _dependencies_satisfied(self, state: _JobState) -> bool:
        for name in state.job.depends_on:
            dependency = self._jobs.get(name)
            if dependency is None:
                return False
            if (
                dependency.in_flight
                or dependency.last_run is None
                or dependency.last_error is not None
            ):
                return False
        return True

    def _dependencies_blockers(self, state: _JobState) -> tuple[str, ...]:
        blockers: list[str] = []
        for name in state.job.depends_on:
            dependency = self._jobs.get(name)
            if dependency is None:
                blockers.append(name)
            elif (
                dependency.in_flight
                or dependency.last_run is None
                or dependency.last_error is not None
            ):
                blockers.append(name)
        return tuple(blockers)

    def _refresh_clock_offset(self) -> None:
        self._clock_offset = float(self._wall_clock()) - float(self._time())

    def _monotonic_from_wall(self, wall_timestamp: float) -> float:
        return wall_timestamp - self._clock_offset

    def _wall_datetime(self) -> datetime:
        return datetime.fromtimestamp(self._wall_clock(), tz=timezone.utc)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.run_pending()
            sleep_for = self._next_sleep_interval()
            if sleep_for > 0:
                self._sleep(sleep_for)

    def _next_sleep_interval(self) -> float:
        with self._lock:
            next_times = [
                state.next_run
                for state in self._jobs.values()
                if state.job.enabled
                and not state.in_flight
                and self._dependencies_satisfied(state)
                and self._accepting_jobs
            ]
        if not next_times:
            return self._idle_sleep
        now = self._time()
        next_run = min(next_times)
        delay = max(0.0, next_run - now)
        return min(delay if delay > 0 else 0.0, self._max_sleep)

    def _wait_for_inflight(self, *, deadline: float | None) -> None:
        while True:
            with self._lock:
                in_progress = any(state.in_flight for state in self._jobs.values())
            if not in_progress:
                return
            if deadline is not None and self._time() >= deadline:
                return
            self._sleep(min(self._idle_sleep, 0.1))


__all__ = [
    "CronExpression",
    "SlaMissedError",
    "StrategyJob",
    "StrategyJobStatus",
    "StrategyScheduler",
]
