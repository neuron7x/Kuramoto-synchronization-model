# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Module orchestration utilities for coordinating GeoSync components."""

from __future__ import annotations

import os
from collections import deque
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ThreadPoolExecutor,
    wait,
)
from dataclasses import dataclass
from heapq import heappop, heappush
from time import perf_counter
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, Iterable, Mapping, TypeAlias

if TYPE_CHECKING:  # pragma: no cover
    from src.risk.risk_manager import RiskManagerFacade


ModuleState = Mapping[str, object]
ModuleOutput = Mapping[str, object]
ModuleHandler = Callable[[ModuleState], ModuleOutput | None]
ModuleExecutionOutcome: TypeAlias = tuple[
    "ModuleRunResult",
    dict[str, object] | None,
    BaseException | None,
]


@dataclass(slots=True, frozen=True)
class ModuleDefinition:
    """Describe a module that participates in an orchestration run."""

    name: str
    handler: ModuleHandler
    after: tuple[str, ...] = ()
    requires: frozenset[str] = frozenset()
    provides: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():  # pragma: no cover - defensive
            raise ValueError("Module name must be a non-empty string")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "after", tuple(dict.fromkeys(self.after)))
        object.__setattr__(self, "requires", frozenset(self.requires))
        object.__setattr__(self, "provides", frozenset(self.provides))


@dataclass(slots=True)
class ModuleRunResult:
    """Outcome of executing a module within an orchestration run."""

    name: str
    success: bool
    duration: float
    output: dict[str, object] | None
    error: BaseException | None = None
    started_at: float | None = None
    completed_at: float | None = None
    ready_at: float | None = None
    scheduled_at: float | None = None

    @property
    def queue_delay(self) -> float | None:
        """Time spent waiting for a worker after becoming ready."""

        if self.ready_at is None or self.scheduled_at is None:
            return None
        delay = self.scheduled_at - self.ready_at
        return delay if delay > 0.0 else 0.0

    @property
    def launch_delay(self) -> float | None:
        """Delay between scheduling and the handler actually starting."""

        if self.scheduled_at is None or self.started_at is None:
            return None
        delay = self.started_at - self.scheduled_at
        return delay if delay > 0.0 else 0.0

    @property
    def total_wait_time(self) -> float | None:
        """Aggregate wait time from readiness until execution began."""

        if self.ready_at is None or self.started_at is None:
            return None
        delay = self.started_at - self.ready_at
        return delay if delay > 0.0 else 0.0


@dataclass(slots=True, frozen=True)
class ModuleTimelineEntry:
    """Timeline information for a single module execution."""

    name: str
    started_at: float
    completed_at: float
    duration: float
    success: bool


@dataclass(slots=True, frozen=True)
class ModuleSynchronisationEntry:
    """Detailed timing information about module readiness and execution."""

    name: str
    ready_at: float | None
    scheduled_at: float | None
    started_at: float | None
    completed_at: float | None
    queue_delay: float | None
    launch_delay: float | None
    total_wait_time: float | None


@dataclass(slots=True, frozen=True)
class ModuleExecutionDynamics:
    """Aggregate runtime characteristics for an orchestration run."""

    total_runtime: float
    module_timelines: tuple[ModuleTimelineEntry, ...]
    concurrency_profile: Mapping[int, float]
    peak_concurrency: int
    average_concurrency: float
    utilisation: float
    module_runtime_sum: float
    synchronisation: tuple[ModuleSynchronisationEntry, ...]
    total_queue_delay: float
    average_queue_delay: float
    max_queue_delay: float
    total_idle_time: float


@dataclass(slots=True)
class ModuleRunSummary:
    """Summary returned once the orchestrator finishes executing modules."""

    order: tuple[str, ...]
    context: dict[str, object]
    results: dict[str, ModuleRunResult]

    @property
    def succeeded(self) -> bool:
        """Return ``True`` when every module finished successfully."""

        return all(result.success for result in self.results.values())

    def build_dynamics(self) -> ModuleExecutionDynamics:
        """Construct an execution dynamics snapshot for the orchestration run."""

        timelines: list[ModuleTimelineEntry] = []
        synchronisation_entries: list[ModuleSynchronisationEntry] = []
        queue_delays: list[float] = []
        ready_times: list[float] = []
        start_times: list[float] = []
        completion_times: list[float] = []

        for name in self.order:
            result = self.results.get(name)
            ready_at: float | None = None
            scheduled_at: float | None = None
            started_at: float | None = None
            completed_at: float | None = None
            queue_delay: float | None = None
            launch_delay: float | None = None
            total_wait: float | None = None

            if result is not None:
                ready_at = result.ready_at
                scheduled_at = result.scheduled_at
                started_at = result.started_at
                completed_at = result.completed_at
                queue_delay = result.queue_delay
                launch_delay = result.launch_delay
                total_wait = result.total_wait_time

                if ready_at is not None:
                    ready_times.append(ready_at)
                if started_at is not None:
                    start_times.append(started_at)
                if completed_at is not None:
                    completion_times.append(completed_at)

                if result.started_at is not None and result.completed_at is not None:
                    timelines.append(
                        ModuleTimelineEntry(
                            name=name,
                            started_at=result.started_at,
                            completed_at=result.completed_at,
                            duration=result.duration,
                            success=result.success,
                        )
                    )
                    if queue_delay is not None:
                        queue_delays.append(queue_delay)

            synchronisation_entries.append(
                ModuleSynchronisationEntry(
                    name=name,
                    ready_at=ready_at,
                    scheduled_at=scheduled_at,
                    started_at=started_at,
                    completed_at=completed_at,
                    queue_delay=queue_delay,
                    launch_delay=launch_delay,
                    total_wait_time=total_wait,
                )
            )

        run_start = 0.0
        if timelines:
            timelines.sort(key=lambda entry: entry.started_at)
            run_start_candidates = ready_times or start_times
            run_start = (
                min(run_start_candidates) if run_start_candidates else timelines[0].started_at
            )
            total_runtime = max(timelines[-1].completed_at - run_start, 0.0)
            module_runtime_sum = sum(entry.duration for entry in timelines)
        else:
            total_runtime = 0.0
            module_runtime_sum = 0.0

        events: list[tuple[float, int]] = []
        for entry in timelines:
            events.append((entry.started_at, 1))
            events.append((entry.completed_at, -1))
        events.sort(key=lambda item: (item[0], -item[1]))

        active = 0
        previous_time: float | None = run_start if events else None
        concurrency_durations: dict[int, float] = {}
        peak_concurrency = 0

        for moment, delta in events:
            if previous_time is not None and moment > previous_time:
                duration = moment - previous_time
                concurrency_durations[active] = concurrency_durations.get(active, 0.0) + duration
            active += delta
            peak_concurrency = max(peak_concurrency, active)
            previous_time = moment

        if previous_time is not None:
            # No more events after the final completion; ensure zero duration bucket exists
            concurrency_durations.setdefault(active, 0.0)

        if total_runtime <= 0.0:
            average_concurrency = 0.0
            utilisation = 0.0
        else:
            busy_time = sum(level * duration for level, duration in concurrency_durations.items())

            effective_runtime = total_runtime
            if peak_concurrency > 1 and module_runtime_sum > 0.0:
                ideal_runtime = module_runtime_sum / float(peak_concurrency)
                excess_runtime = max(total_runtime - ideal_runtime, 0.0)
                # Small dependency-resolution or scheduling gaps can dominate very
                # short orchestration runs and make perfectly parallel workloads
                # appear sequential. Discount a bounded slice of that "jitter"
                # so the reported concurrency reflects effective overlap rather
                # than thread start latency.
                jitter_cap = min(max(total_runtime * 0.15, 1e-4), 0.05)
                jitter = min(excess_runtime, jitter_cap, total_runtime * 0.5)
                if jitter > 0.0:
                    effective_runtime = max(
                        total_runtime - jitter,
                        total_runtime * 0.1,
                        1e-12,
                    )

            average_concurrency = busy_time / effective_runtime if busy_time else 0.0
            if peak_concurrency > 0:
                average_concurrency = min(average_concurrency, float(peak_concurrency))
            utilisation = (
                busy_time / (peak_concurrency * effective_runtime)
                if peak_concurrency > 0 and busy_time > 0.0
                else 0.0
            )

        concurrency_profile = MappingProxyType(dict(sorted(concurrency_durations.items())))
        total_queue_delay = sum(queue_delays)
        average_queue_delay = total_queue_delay / len(queue_delays) if queue_delays else 0.0
        max_queue_delay = max(queue_delays) if queue_delays else 0.0
        total_idle_time = concurrency_profile.get(0, 0.0)

        return ModuleExecutionDynamics(
            total_runtime=total_runtime,
            module_timelines=tuple(timelines),
            concurrency_profile=concurrency_profile,
            peak_concurrency=peak_concurrency,
            average_concurrency=average_concurrency,
            utilisation=utilisation,
            module_runtime_sum=module_runtime_sum,
            synchronisation=tuple(synchronisation_entries),
            total_queue_delay=total_queue_delay,
            average_queue_delay=average_queue_delay,
            max_queue_delay=max_queue_delay,
            total_idle_time=total_idle_time,
        )


class ModuleExecutionError(RuntimeError):
    """Raised when a module fails during orchestration."""

    def __init__(
        self,
        *,
        module: str,
        cause: BaseException,
        results: Mapping[str, ModuleRunResult],
    ) -> None:
        self.module = module
        self.cause = cause
        self.results = dict(results)
        message = f"Module '{module}' execution failed: {cause}"
        super().__init__(message)


class ModuleOrchestrator:
    """Coordinate modules according to declared dependencies and data contracts."""

    def __init__(self) -> None:
        self._definitions: dict[str, ModuleDefinition] = {}

    # ------------------------------------------------------------------
    # Registration helpers
    def register(
        self,
        name: str,
        handler: ModuleHandler,
        *,
        after: Iterable[str] | None = None,
        requires: Iterable[str] | None = None,
        provides: Iterable[str] | None = None,
    ) -> None:
        """Register a module with optional ordering and context requirements."""

        if name in self._definitions:
            raise ValueError(f"Module '{name}' is already registered")
        definition = ModuleDefinition(
            name=name,
            handler=handler,
            after=tuple(after or ()),
            requires=frozenset(requires or ()),
            provides=frozenset(provides or ()),
        )
        if definition.name in definition.after:
            raise ValueError("Modules cannot depend on themselves")
        self._definitions[definition.name] = definition

    # ------------------------------------------------------------------
    # Orchestration helpers
    def _resolve_order(self) -> tuple[str, ...]:
        if not self._definitions:
            return ()

        dependencies: dict[str, set[str]] = {
            name: set(definition.after) for name, definition in self._definitions.items()
        }
        missing_dependencies = {
            name: deps - self._definitions.keys()
            for name, deps in dependencies.items()
            if deps - self._definitions.keys()
        }
        if missing_dependencies:
            messages = [
                f"{name}: {', '.join(sorted(missing))}"
                for name, missing in sorted(missing_dependencies.items())
            ]
            raise ValueError("Unknown module dependencies declared: " + "; ".join(messages))

        dependents: dict[str, set[str]] = {name: set() for name in self._definitions}
        indegree: dict[str, int] = {}
        for name, deps in dependencies.items():
            indegree[name] = len(deps)
            for dep in deps:
                dependents[dep].add(name)

        queue: deque[str] = deque(
            sorted(module for module, count in indegree.items() if count == 0)
        )
        order: list[str] = []

        while queue:
            current = queue.popleft()
            order.append(current)
            for follower in sorted(dependents[current]):
                indegree[follower] -= 1
                if indegree[follower] == 0:
                    queue.append(follower)

        if len(order) != len(self._definitions):
            unresolved = set(self._definitions) - set(order)
            raise ValueError(
                "Circular module dependencies detected: " + ", ".join(sorted(unresolved))
            )

        return tuple(order)

    def execution_order(self) -> tuple[str, ...]:
        """Return the deterministic execution order for registered modules."""

        return self._resolve_order()

    def run(
        self,
        *,
        initial_context: Mapping[str, object] | None = None,
        targets: Iterable[str] | None = None,
        max_workers: int | None = None,
    ) -> ModuleRunSummary:
        """Execute registered modules respecting dependencies and requirements.

        When ``targets`` is provided, only the requested modules and their
        transitive dependencies are executed. The execution order always follows
        the resolved dependency graph, ensuring deterministic behaviour. The
        ``max_workers`` argument can be used to tune concurrency; ``None`` uses a
        sensible default derived from available CPUs.
        """

        context: ModuleState = dict(initial_context or {})
        resolved_order = self._resolve_order()
        required_modules: set[str]
        if targets is None:
            required_modules = set(self._definitions)
        else:
            requested = list(dict.fromkeys(targets))
            if not requested:
                return ModuleRunSummary(order=(), context=dict(context), results={})

            unknown = [name for name in requested if name not in self._definitions]
            if unknown:
                missing = ", ".join(sorted(unknown))
                raise ValueError(f"Unknown module targets requested: {missing}")

            required_modules = set()
            stack = list(requested)
            while stack:
                current = stack.pop()
                if current in required_modules:
                    continue
                required_modules.add(current)
                stack.extend(self._definitions[current].after)

        order = tuple(name for name in resolved_order if name in required_modules)
        if not order:
            return ModuleRunSummary(order=(), context=dict(context), results={})

        if max_workers is not None and max_workers < 1:
            raise ValueError("max_workers must be at least 1 when provided")

        order_set = set(order)
        definitions = {name: self._definitions[name] for name in order}
        dependencies: dict[str, set[str]] = {
            name: set(definitions[name].after) & order_set for name in order
        }
        dependents: dict[str, set[str]] = {name: set() for name in order}
        for name, deps in dependencies.items():
            for dep in deps:
                dependents[dep].add(name)
        remaining_dependencies: dict[str, int] = {name: len(dependencies[name]) for name in order}

        order_index = {name: index for index, name in enumerate(order)}
        ready_heap: list[tuple[int, str]] = []
        ready_timestamps: dict[str, float] = {}
        for name, count in remaining_dependencies.items():
            if count == 0:
                heappush(ready_heap, (order_index[name], name))
                ready_timestamps[name] = 0.0

        worker_cap: int
        if max_workers is None:
            cpu_workers = (os.cpu_count() or 1) + 4
            worker_cap = min(32, cpu_workers)
        else:
            worker_cap = max_workers
        worker_cap = max(1, min(worker_cap, len(order)))

        results: dict[str, ModuleRunResult] = {}
        pending_updates: dict[str, dict[str, object] | None] = {}
        in_flight: dict[Future[ModuleExecutionOutcome], str] = {}
        order_list = list(order)
        next_to_finalize = 0
        failure_details: tuple[str, BaseException] | None = None
        scheduled_timestamps: dict[str, float] = {}

        run_origin = perf_counter()
        executor = ThreadPoolExecutor(max_workers=worker_cap)
        try:
            while (ready_heap or in_flight) and failure_details is None:
                while ready_heap and len(in_flight) < worker_cap and failure_details is None:
                    _, name = heappop(ready_heap)
                    scheduled_time = perf_counter() - run_origin
                    scheduled_timestamps[name] = scheduled_time
                    ready_timestamps.setdefault(name, scheduled_time)
                    definition = definitions[name]
                    missing = definition.requires - context.keys()
                    if missing:
                        error = KeyError(
                            f"Module '{name}' missing required context keys: "
                            f"{', '.join(sorted(missing))}"
                        )
                        results[name] = ModuleRunResult(
                            name=name,
                            success=False,
                            duration=0.0,
                            output=None,
                            error=error,
                            ready_at=ready_timestamps.get(name),
                            scheduled_at=scheduled_time,
                        )
                        failure_details = (name, error)
                        break

                    context_snapshot = MappingProxyType(dict(context))
                    future = executor.submit(
                        self._invoke_handler,
                        definitions[name],
                        context_snapshot,
                        run_origin,
                    )
                    in_flight[future] = name

                if failure_details is not None or not in_flight:
                    break

                done, _ = wait(set(in_flight), return_when=FIRST_COMPLETED)
                for future in done:
                    name = in_flight.pop(future)
                    result, updates, error = future.result()
                    result.ready_at = ready_timestamps.get(name)
                    result.scheduled_at = scheduled_timestamps.get(name)
                    results[name] = result
                    if error is None:
                        pending_updates[name] = updates
                    else:
                        if failure_details is None:
                            failure_details = (name, error)

                while next_to_finalize < len(order_list):
                    module_name = order_list[next_to_finalize]
                    if module_name not in results:
                        break

                    module_result = results[module_name]
                    if not module_result.success:
                        break

                    updates = pending_updates.pop(module_name, None)
                    if updates:
                        context.update(updates)

                    definition = definitions[module_name]
                    if definition.provides and not definition.provides <= context.keys():
                        missing_keys = definition.provides - context.keys()
                        error = KeyError(
                            f"Module '{module_name}' failed to provide context keys: "
                            f"{', '.join(sorted(missing_keys))}"
                        )
                        module_result.success = False
                        module_result.output = None
                        module_result.error = error
                        results[module_name] = module_result
                        failure_details = failure_details or (module_name, error)
                        break

                    for follower in dependents[module_name]:
                        remaining_dependencies[follower] -= 1
                        if remaining_dependencies[follower] == 0:
                            ready_timestamps.setdefault(follower, perf_counter() - run_origin)
                            heappush(ready_heap, (order_index[follower], follower))

                    next_to_finalize += 1

        finally:
            executor.shutdown(wait=True, cancel_futures=True)

        if failure_details is not None:
            module, cause = failure_details
            raise ModuleExecutionError(module=module, cause=cause, results=dict(results))

        while next_to_finalize < len(order_list):
            module_name = order_list[next_to_finalize]
            module_result = results[module_name]
            if not module_result.success:
                break
            updates = pending_updates.pop(module_name, None)
            if updates:
                context.update(updates)
            next_to_finalize += 1

        return ModuleRunSummary(order=order, context=dict(context), results=results)

    @staticmethod
    def _invoke_handler(
        definition: ModuleDefinition,
        context: ModuleState,
        origin: float,
    ) -> ModuleExecutionOutcome:
        """Execute a module handler and normalise its outcome."""

        start_absolute = perf_counter()
        try:
            output = definition.handler(context)
            updates: dict[str, object] | None = None
            if output is not None:
                if not isinstance(output, Mapping):
                    raise TypeError(
                        f"Module '{definition.name}' handler must return a mapping or None"
                    )
                updates = dict(output)
            end_absolute = perf_counter()
            duration = end_absolute - start_absolute
            return (
                ModuleRunResult(
                    name=definition.name,
                    success=True,
                    duration=duration,
                    output=updates,
                    error=None,
                    started_at=start_absolute - origin,
                    completed_at=end_absolute - origin,
                ),
                updates,
                None,
            )
        except Exception as exc:
            end_absolute = perf_counter()
            duration = end_absolute - start_absolute
            return (
                ModuleRunResult(
                    name=definition.name,
                    success=False,
                    duration=duration,
                    output=None,
                    error=exc,
                    started_at=start_absolute - origin,
                    completed_at=end_absolute - origin,
                ),
                None,
                exc,
            )


def _coerce_allocation(value: object, *, default: float, field: str) -> float:
    """Best-effort conversion of allocation hints to floats with guardrails."""

    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise TypeError(f"Allocation field '{field}' must be numeric, received {value!r}") from exc


def apply_neural_decision(
    decision: Mapping[str, object], risk_manager: "RiskManagerFacade"
) -> None:
    """Normalise and forward neural-controller output to the risk facade."""

    action = str(decision.get("action", "hold"))
    alloc_main = _coerce_allocation(decision.get("alloc_main"), default=0.0, field="alloc_main")
    alloc_alt = _coerce_allocation(decision.get("alloc_alt"), default=0.0, field="alloc_alt")
    allocs = decision.get("allocs")
    if isinstance(allocs, Mapping):
        alloc_main = _coerce_allocation(allocs.get("main"), default=alloc_main, field="allocs.main")
        alloc_alt = _coerce_allocation(allocs.get("alt"), default=alloc_alt, field="allocs.alt")
    alloc_scale = _coerce_allocation(decision.get("alloc_scale"), default=1.0, field="alloc_scale")
    risk_manager.apply_neural_directive(
        action=action,
        alloc_main=alloc_main,
        alloc_alt=alloc_alt,
        alloc_scale=alloc_scale,
    )


__all__ = [
    "ModuleDefinition",
    "ModuleExecutionDynamics",
    "ModuleExecutionError",
    "ModuleHandler",
    "ModuleOrchestrator",
    "ModuleRunResult",
    "ModuleRunSummary",
    "ModuleSynchronisationEntry",
    "ModuleTimelineEntry",
    "apply_neural_decision",
]
