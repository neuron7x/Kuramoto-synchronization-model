from __future__ import annotations

from collections import deque
from typing import Mapping

import pytest

from src.system import (
    ModuleExecutionError,
    ModuleOrchestrator,
    ModuleRunResult,
    ModuleRunSummary,
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

