"""Module orchestration utilities for coordinating TradePulse components."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Iterable, Mapping, MutableMapping


ModuleState = MutableMapping[str, object]
ModuleOutput = Mapping[str, object]
ModuleHandler = Callable[[ModuleState], ModuleOutput | None]


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
    ) -> ModuleRunSummary:
        """Execute all registered modules according to their dependencies."""

        context: ModuleState = dict(initial_context or {})
        order = self._resolve_order()
        results: dict[str, ModuleRunResult] = {}

        for name in order:
            definition = self._definitions[name]
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
                raise ModuleExecutionError(module=name, cause=error, results=results)

            start = perf_counter()
            try:
                output = definition.handler(context)
                updates: dict[str, object] | None = None
                if output is not None:
                    if not isinstance(output, Mapping):
                        raise TypeError(
                            f"Module '{name}' handler must return a mapping or None"
                        )
                    updates = dict(output)
                    context.update(updates)

                if definition.provides and not definition.provides <= context.keys():
                    missing_keys = definition.provides - context.keys()
                    raise KeyError(
                        f"Module '{name}' failed to provide context keys: "
                        f"{', '.join(sorted(missing_keys))}"
                    )

            except Exception as exc:
                duration = perf_counter() - start
                results[name] = ModuleRunResult(
                    name=name,
                    success=False,
                    duration=duration,
                    output=None,
                    error=exc,
                )
                raise ModuleExecutionError(module=name, cause=exc, results=results) from exc

            duration = perf_counter() - start
            results[name] = ModuleRunResult(
                name=name,
                success=True,
                duration=duration,
                output=updates,
                error=None,
            )

        return ModuleRunSummary(order=order, context=dict(context), results=results)


__all__ = [
    "ModuleDefinition",
    "ModuleExecutionError",
    "ModuleHandler",
    "ModuleOrchestrator",
    "ModuleRunResult",
    "ModuleRunSummary",
]

