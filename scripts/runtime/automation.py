# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Composable automation helpers for multi-step maintenance workflows."""

from __future__ import annotations

import threading

# SPDX-License-Identifier: MIT
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Iterable, Mapping


class StepStatus(str, Enum):
    """Enumeration of terminal statuses for automation steps."""

    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(slots=True)
class StepResult:
    """Outcome details for an executed automation step."""

    name: str
    status: StepStatus
    attempts: int
    started_at: datetime | None
    completed_at: datetime | None
    output: Any = None
    error: BaseException | None = None
    critical: bool = True
    description: str | None = None

    @property
    def duration(self) -> float:
        """Return the wall-clock runtime for the step in seconds."""

        if self.started_at is None or self.completed_at is None:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds()


class AutomationContext:
    """Container for sharing state across automation steps."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._outputs: dict[str, Any] = {}
        self._results: OrderedDict[str, StepResult] = OrderedDict()
        self.data: dict[str, Any] = {}

    def get_output(self, name: str, default: Any | None = None) -> Any | None:
        """Return the recorded output for *name*, or *default* when absent."""

        with self._lock:
            return self._outputs.get(name, default)

    def require_output(self, name: str) -> Any:
        """Return the recorded output for *name*, raising if unavailable."""

        with self._lock:
            if name not in self._outputs:
                raise KeyError(f"Output for step '{name}' is unavailable")
            return self._outputs[name]

    def record_result(self, result: StepResult) -> None:
        """Persist *result* and update the output cache when relevant."""

        with self._lock:
            self._results[result.name] = result
            if result.status is StepStatus.SUCCEEDED:
                self._outputs[result.name] = result.output

    def results(self) -> Mapping[str, StepResult]:
        """Return a snapshot of all recorded results in execution order."""

        with self._lock:
            return OrderedDict(self._results)


AutomationAction = Callable[[AutomationContext], Any]
SkipPredicate = Callable[[AutomationContext], bool]


@dataclass(slots=True)
class AutomationStep:
    """Declarative description of a single automation step."""

    name: str
    action: AutomationAction
    dependencies: tuple[str, ...] = ()
    retry_attempts: int = 0
    critical: bool = True
    skip_if: SkipPredicate | None = None
    description: str | None = None


@dataclass(slots=True)
class AutomationReport:
    """Summary of an automation run."""

    results: OrderedDict[str, StepResult]
    started_at: datetime
    completed_at: datetime

    @property
    def succeeded(self) -> bool:
        """Return ``True`` when every step either succeeded or was skipped."""

        return all(
            result.status in {StepStatus.SUCCEEDED, StepStatus.SKIPPED}
            for result in self.results.values()
        )

    @property
    def failed_steps(self) -> list[StepResult]:
        """Return the subset of steps that failed or were blocked."""

        return [
            result
            for result in self.results.values()
            if result.status in {StepStatus.FAILED, StepStatus.BLOCKED}
        ]


class AutomationRunner:
    """Execute a directed acyclic graph of :class:`AutomationStep` objects."""

    def __init__(self, steps: Iterable[AutomationStep]) -> None:
        self._steps = list(steps)
        if not self._steps:
            raise ValueError("At least one automation step is required")
        self._step_map = {step.name: step for step in self._steps}
        if len(self._step_map) != len(self._steps):
            raise ValueError("Automation step names must be unique")
        self._validate_dependencies()
        self._order = self._topological_order()

    def _validate_dependencies(self) -> None:
        for step in self._steps:
            for dependency in step.dependencies:
                if dependency not in self._step_map:
                    raise ValueError(f"Step '{step.name}' depends on unknown step '{dependency}'")

    def _topological_order(self) -> list[str]:
        adjacency: dict[str, set[str]] = {step.name: set() for step in self._steps}
        indegree: dict[str, int] = {step.name: 0 for step in self._steps}
        for step in self._steps:
            for dependency in step.dependencies:
                adjacency[dependency].add(step.name)
                indegree[step.name] += 1

        queue = deque(
            sorted(
                (name for name, count in indegree.items() if count == 0),
                key=lambda item: self._index_of(item),
            )
        )
        order: list[str] = []
        while queue:
            current = queue.popleft()
            order.append(current)
            for successor in sorted(adjacency[current], key=lambda item: self._index_of(item)):
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    queue.append(successor)

        if len(order) != len(self._steps):
            raise ValueError("Cycle detected in automation dependency graph")
        return order

    def _index_of(self, name: str) -> int:
        for index, step in enumerate(self._steps):
            if step.name == name:
                return index
        raise KeyError(name)

    def run(self, context: AutomationContext | None = None) -> AutomationReport:
        """Execute the configured steps and return a comprehensive report."""

        context = context or AutomationContext()
        started_at = datetime.now(timezone.utc)
        blocked = False
        for name in self._order:
            step = self._step_map[name]
            dependencies = [context.results().get(dep) for dep in step.dependencies]
            if any(
                dependency is None
                or dependency.status not in {StepStatus.SUCCEEDED, StepStatus.SKIPPED}
                for dependency in dependencies
            ):
                context.record_result(
                    StepResult(
                        name=step.name,
                        status=StepStatus.BLOCKED,
                        attempts=0,
                        started_at=None,
                        completed_at=None,
                        critical=step.critical,
                        description=step.description,
                    )
                )
                continue

            if blocked:
                context.record_result(
                    StepResult(
                        name=step.name,
                        status=StepStatus.BLOCKED,
                        attempts=0,
                        started_at=None,
                        completed_at=None,
                        critical=step.critical,
                        description=step.description,
                    )
                )
                continue

            if step.skip_if and step.skip_if(context):
                context.record_result(
                    StepResult(
                        name=step.name,
                        status=StepStatus.SKIPPED,
                        attempts=0,
                        started_at=None,
                        completed_at=None,
                        critical=step.critical,
                        description=step.description,
                    )
                )
                continue

            attempts = 0
            started = datetime.now(timezone.utc)
            error: BaseException | None = None
            output: Any = None
            status = StepStatus.FAILED
            for attempt in range(step.retry_attempts + 1):
                attempts = attempt + 1
                try:
                    output = step.action(context)
                    status = StepStatus.SUCCEEDED
                    error = None
                    break
                except Exception as exc:
                    error = exc
                    if attempt == step.retry_attempts:
                        status = StepStatus.FAILED

            finished = datetime.now(timezone.utc)
            result = StepResult(
                name=step.name,
                status=status,
                attempts=attempts,
                started_at=started,
                completed_at=finished,
                output=output,
                error=error,
                critical=step.critical,
                description=step.description,
            )
            context.record_result(result)

            if status is StepStatus.FAILED and step.critical:
                blocked = True

        completed_at = datetime.now(timezone.utc)
        return AutomationReport(
            results=OrderedDict(context.results()),
            started_at=started_at,
            completed_at=completed_at,
        )
