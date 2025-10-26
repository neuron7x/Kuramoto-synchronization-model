"""Module orchestration utilities for coordinating TradePulse components."""

from __future__ import annotations

from collections import deque
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ThreadPoolExecutor,
    wait,
)
from dataclasses import dataclass
import os
from heapq import heappop, heappush
from time import perf_counter
from types import MappingProxyType
from typing import Callable, Iterable, Mapping, TypeAlias


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
            raise ValueError(
                "Unknown module dependencies declared: " + "; ".join(messages)
            )

        dependents: dict[str, set[str]] = {
            name: set() for name in self._definitions
        }
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
                "Circular module dependencies detected: "
                + ", ".join(sorted(unresolved))
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

        order = tuple(
            name for name in resolved_order if name in required_modules
        )
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
        remaining_dependencies: dict[str, int] = {
            name: len(dependencies[name]) for name in order
        }

        order_index = {name: index for index, name in enumerate(order)}
        ready_heap: list[tuple[int, str]] = []
        for name, count in remaining_dependencies.items():
            if count == 0:
                heappush(ready_heap, (order_index[name], name))

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

        executor = ThreadPoolExecutor(max_workers=worker_cap)
        try:
            while (ready_heap or in_flight) and failure_details is None:
                while (
                    ready_heap
                    and len(in_flight) < worker_cap
                    and failure_details is None
                ):
                    _, name = heappop(ready_heap)
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
                        )
                        failure_details = (name, error)
                        break

                    context_snapshot = MappingProxyType(dict(context))
                    future = executor.submit(
                        self._invoke_handler, definitions[name], context_snapshot
                    )
                    in_flight[future] = name

                if failure_details is not None or not in_flight:
                    break

                done, _ = wait(set(in_flight), return_when=FIRST_COMPLETED)
                for future in done:
                    name = in_flight.pop(future)
                    result, updates, error = future.result()
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
                        results[module_name] = ModuleRunResult(
                            name=module_name,
                            success=False,
                            duration=module_result.duration,
                            output=None,
                            error=error,
                        )
                        failure_details = failure_details or (module_name, error)
                        break

                    for follower in dependents[module_name]:
                        remaining_dependencies[follower] -= 1
                        if remaining_dependencies[follower] == 0:
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
    ) -> ModuleExecutionOutcome:
        """Execute a module handler and normalise its outcome."""

        start = perf_counter()
        try:
            output = definition.handler(context)
            updates: dict[str, object] | None = None
            if output is not None:
                if not isinstance(output, Mapping):
                    raise TypeError(
                        f"Module '{definition.name}' handler must return a mapping or None"
                    )
                updates = dict(output)
            duration = perf_counter() - start
            return (
                ModuleRunResult(
                    name=definition.name,
                    success=True,
                    duration=duration,
                    output=updates,
                    error=None,
                ),
                updates,
                None,
            )
        except Exception as exc:
            duration = perf_counter() - start
            return (
                ModuleRunResult(
                    name=definition.name,
                    success=False,
                    duration=duration,
                    output=None,
                    error=exc,
                ),
                None,
                exc,
            )


__all__ = [
    "ModuleDefinition",
    "ModuleExecutionError",
    "ModuleHandler",
    "ModuleOrchestrator",
    "ModuleRunResult",
    "ModuleRunSummary",
]

