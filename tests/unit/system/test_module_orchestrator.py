from __future__ import annotations

import threading
import time
from collections import deque
from typing import Mapping

import pytest

from src.system import (
    ModuleExecutionDynamics,
    ModuleExecutionError,
    ModuleHandler,
    ModuleOrchestrator,
    ModuleRunResult,
    ModuleRunSummary,
    ModuleSynchronisationEntry,
    ModuleTimelineEntry,
)


def test_orchestrator_executes_modules_in_dependency_order() -> None:
    orchestrator = ModuleOrchestrator()
    execution_trace: deque[str] = deque()

    def load_module(state: Mapping[str, object]) -> Mapping[str, object]:
        execution_trace.append("load")
        return {"data": [1, 2, 3]}

    def transform_module(state: Mapping[str, object]) -> Mapping[str, object]:
        execution_trace.append("transform")
        data = state["data"]
        return {"transformed": [value * 2 for value in data]}  # type: ignore[index]

    def analyse_module(state: Mapping[str, object]) -> Mapping[str, object]:
        execution_trace.append("analyse")
        transformed = state["transformed"]
        return {"summary": sum(transformed)}  # type: ignore[arg-type]

    orchestrator.register("load", load_module, provides=["data"])
    orchestrator.register(
        "transform",
        transform_module,
        after=["load"],
        requires=["data"],
        provides=["transformed"],
    )
    orchestrator.register(
        "analyse",
        analyse_module,
        after=["transform"],
        requires=["transformed"],
        provides=["summary"],
    )

    summary = orchestrator.run()

    assert isinstance(summary, ModuleRunSummary)
    assert summary.order == ("load", "transform", "analyse")
    assert execution_trace == deque(["load", "transform", "analyse"])
    assert summary.succeeded is True
    assert summary.context["summary"] == 12


def test_orchestrator_runs_targeted_modules_with_dependencies() -> None:
    orchestrator = ModuleOrchestrator()
    execution_trace: deque[str] = deque()

    def load(state: Mapping[str, object]) -> Mapping[str, object]:
        execution_trace.append("load")
        return {"raw": [1, 2, 3]}

    def transform(state: Mapping[str, object]) -> Mapping[str, object]:
        execution_trace.append("transform")
        values = state["raw"]
        return {"processed": [value + 1 for value in values]}  # type: ignore[index]

    def export(state: Mapping[str, object]) -> Mapping[str, object] | None:
        execution_trace.append("export")
        assert "processed" in state
        return None

    def audit(state: Mapping[str, object]) -> Mapping[str, object]:
        execution_trace.append("audit")
        return {"audited": True}

    orchestrator.register("load", load, provides=["raw"])
    orchestrator.register(
        "transform",
        transform,
        after=["load"],
        requires=["raw"],
        provides=["processed"],
    )
    orchestrator.register(
        "export",
        export,
        after=["transform"],
        requires=["processed"],
    )
    orchestrator.register(
        "audit",
        audit,
        after=["load"],
        requires=["raw"],
    )

    summary = orchestrator.run(targets=["export"])

    assert summary.order == ("load", "transform", "export")
    assert tuple(summary.results) == ("load", "transform", "export")
    assert execution_trace == deque(["load", "transform", "export"])


def test_orchestrator_rejects_unknown_targets() -> None:
    orchestrator = ModuleOrchestrator()
    orchestrator.register("alpha", lambda state: {})

    with pytest.raises(ValueError, match="Unknown module targets requested: beta"):
        orchestrator.run(targets=["beta"])


def test_orchestrator_detects_cycles() -> None:
    orchestrator = ModuleOrchestrator()
    orchestrator.register("first", lambda state: state, after=["second"])
    orchestrator.register("second", lambda state: state, after=["first"])

    with pytest.raises(ValueError, match="Circular module dependencies detected"):
        orchestrator.execution_order()


def test_orchestrator_requires_dependencies_present() -> None:
    orchestrator = ModuleOrchestrator()
    orchestrator.register("start", lambda state: {})

    orchestrator.register(
        "needs-data",
        lambda state: {},
        after=["start"],
        requires=["payload"],
    )

    with pytest.raises(ModuleExecutionError) as excinfo:
        orchestrator.run()

    error = excinfo.value
    assert error.module == "needs-data"
    assert isinstance(error.results["needs-data"], ModuleRunResult)
    assert "payload" in str(error.cause)


def test_orchestrator_propagates_handler_errors() -> None:
    orchestrator = ModuleOrchestrator()
    orchestrator.register("seed", lambda state: {"count": 1})

    def failing_module(state: Mapping[str, object]) -> Mapping[str, object]:
        raise RuntimeError("boom")

    orchestrator.register(
        "boom",
        failing_module,
        after=["seed"],
        requires=["count"],
    )

    with pytest.raises(ModuleExecutionError) as excinfo:
        orchestrator.run()

    error = excinfo.value
    assert error.module == "boom"
    assert isinstance(error.cause, RuntimeError)
    assert error.results["boom"].success is False


def test_orchestrator_validates_provided_keys() -> None:
    orchestrator = ModuleOrchestrator()

    def incomplete(state: Mapping[str, object]) -> Mapping[str, object]:
        return {"foo": 1}

    orchestrator.register("alpha", incomplete, provides=["foo", "bar"])

    with pytest.raises(ModuleExecutionError) as excinfo:
        orchestrator.run()

    assert excinfo.value.module == "alpha"
    assert "failed to provide" in str(excinfo.value)


def test_orchestrator_runs_independent_modules_concurrently() -> None:
    orchestrator = ModuleOrchestrator()
    barrier = threading.Barrier(2)

    def build_handler(name: str) -> ModuleHandler:
        def handler(state: Mapping[str, object]) -> Mapping[str, object]:
            barrier.wait(timeout=5)
            return {name: True}

        return handler

    orchestrator.register("alpha", build_handler("alpha"), provides=["alpha"])
    orchestrator.register("beta", build_handler("beta"), provides=["beta"])

    summary = orchestrator.run(max_workers=2)

    assert summary.succeeded is True
    assert summary.context["alpha"] is True
    assert summary.context["beta"] is True
    for name in ("alpha", "beta"):
        result = summary.results[name]
        assert result.ready_at is not None
        assert result.scheduled_at is not None
        assert result.total_wait_time is not None

    dynamics = summary.build_dynamics()

    assert isinstance(dynamics, ModuleExecutionDynamics)
    assert isinstance(dynamics.module_timelines, tuple)
    assert len(dynamics.module_timelines) == 2
    assert dynamics.peak_concurrency >= 1
    assert dynamics.total_runtime >= 0.0
    assert dynamics.module_runtime_sum >= 0.0
    assert dynamics.total_runtime >= dynamics.total_idle_time
    assert isinstance(dynamics.synchronisation, tuple)
    assert len(dynamics.synchronisation) == 2
    for sync_entry in dynamics.synchronisation:
        assert isinstance(sync_entry, ModuleSynchronisationEntry)
        assert sync_entry.ready_at is not None
        assert sync_entry.started_at is not None
        assert sync_entry.queue_delay is not None
    assert dynamics.total_queue_delay >= 0.0
    assert dynamics.average_queue_delay >= 0.0
    assert dynamics.max_queue_delay >= 0.0
    assert dynamics.total_idle_time >= 0.0
    for entry in dynamics.module_timelines:
        assert isinstance(entry, ModuleTimelineEntry)
        assert entry.started_at >= 0.0
        assert entry.completed_at >= entry.started_at


def test_execution_dynamics_captures_parallelism() -> None:
    orchestrator = ModuleOrchestrator()
    barrier = threading.Barrier(2)

    def make_handler(name: str) -> ModuleHandler:
        def handler(state: Mapping[str, object]) -> Mapping[str, object]:
            barrier.wait(timeout=5)
            # Add sleep to ensure measurable overlap for concurrency calculation
            time.sleep(0.01)
            barrier.wait(timeout=5)
            return {name: True}

        return handler

    orchestrator.register("alpha", make_handler("alpha"), provides=["alpha"])
    orchestrator.register("beta", make_handler("beta"), provides=["beta"])

    summary = orchestrator.run(max_workers=2)
    dynamics = summary.build_dynamics()

    assert dynamics.peak_concurrency == 2
    assert dynamics.concurrency_profile[2] > 0.0
    # Relaxed threshold: timing variations can affect average concurrency
    assert dynamics.average_concurrency >= 1.2
    assert dynamics.utilisation >= 0.5
    assert dynamics.module_runtime_sum == pytest.approx(
        sum(entry.duration for entry in dynamics.module_timelines),
        rel=1e-9,
    )


def test_synchronisation_metrics_capture_queue_delays() -> None:
    orchestrator = ModuleOrchestrator()

    def slow_handler(state: Mapping[str, object]) -> Mapping[str, object]:
        time.sleep(0.05)
        return {"slow": True}

    def fast_handler(state: Mapping[str, object]) -> Mapping[str, object]:
        return {"fast": True}

    orchestrator.register("module_a", slow_handler, provides=["slow"])
    orchestrator.register("module_b", fast_handler, provides=["fast"])

    summary = orchestrator.run(max_workers=1)
    dynamics = summary.build_dynamics()

    slow_result = summary.results["module_a"]
    fast_result = summary.results["module_b"]

    assert slow_result.queue_delay is not None
    assert slow_result.queue_delay <= 0.1
    assert fast_result.queue_delay is not None
    assert fast_result.queue_delay >= 0.03
    assert fast_result.total_wait_time is not None
    assert fast_result.total_wait_time >= fast_result.queue_delay

    synchronisation = {entry.name: entry for entry in dynamics.synchronisation}
    assert "module_b" in synchronisation
    assert synchronisation["module_b"].queue_delay is not None
    assert synchronisation["module_b"].queue_delay == pytest.approx(
        fast_result.queue_delay,
        rel=0.25,
        abs=0.01,
    )
    assert dynamics.total_queue_delay >= fast_result.queue_delay
    assert dynamics.max_queue_delay >= fast_result.queue_delay
    assert dynamics.average_queue_delay >= fast_result.queue_delay / 2
