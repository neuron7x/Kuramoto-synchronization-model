"""Tests covering orchestration invariants and neural decision normalisation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from src.system.module_orchestrator import (
    ModuleExecutionError,
    ModuleOrchestrator,
    ModuleRunResult,
    ModuleRunSummary,
    apply_neural_decision,
)


def test_orchestrator_run_executes_dependencies_and_updates_context() -> None:
    orchestrator = ModuleOrchestrator()
    execution_order: list[str] = []

    def alpha(context: Mapping[str, object]) -> Mapping[str, object]:
        execution_order.append("alpha")
        assert context["seed"] == 3
        return {"alpha": 1, "shared": "alpha"}

    def beta(context: Mapping[str, object]) -> Mapping[str, object]:
        execution_order.append("beta")
        assert context["alpha"] == 1
        return {"beta": 2, "shared": "beta"}

    def gamma(context: Mapping[str, object]) -> None:
        execution_order.append("gamma")
        assert context["beta"] == 2
        assert context["shared"] == "beta"
        return None

    orchestrator.register(
        "alpha",
        alpha,
        provides={"alpha", "shared"},
    )
    orchestrator.register(
        "beta",
        beta,
        after=("alpha",),
        requires={"alpha"},
        provides={"beta", "shared"},
    )
    orchestrator.register(
        "gamma",
        gamma,
        after=("beta",),
        requires={"beta", "shared"},
    )

    summary = orchestrator.run(initial_context={"seed": 3})

    assert summary.order == ("alpha", "beta", "gamma")
    assert summary.context["alpha"] == 1
    assert summary.context["beta"] == 2
    assert summary.context["shared"] == "beta"
    assert execution_order == ["alpha", "beta", "gamma"]
    assert summary.succeeded is True


def test_orchestrator_targets_include_transitive_dependencies_only() -> None:
    orchestrator = ModuleOrchestrator()
    orchestrator.register("alpha", lambda _: {"alpha": 1})
    orchestrator.register(
        "beta",
        lambda ctx: {"beta": ctx["alpha"] + 1},
        after=("alpha",),
        requires={"alpha"},
    )
    orchestrator.register(
        "gamma",
        lambda ctx: {"gamma": ctx["beta"] + 1},
        after=("beta",),
        requires={"beta"},
    )
    executed: list[str] = []

    def delta(context: Mapping[str, object]) -> Mapping[str, object]:
        executed.append("delta")
        return {"delta": context.get("gamma", 0)}

    orchestrator.register("delta", delta)

    summary = orchestrator.run(targets=("gamma",))

    assert summary.order == ("alpha", "beta", "gamma")
    assert "delta" not in summary.results
    assert summary.context["gamma"] == 3
    assert executed == []


def test_orchestrator_failure_includes_partial_results() -> None:
    orchestrator = ModuleOrchestrator()

    orchestrator.register("alpha", lambda _: {"alpha": 1})

    def failing(_: Mapping[str, object]) -> None:
        raise RuntimeError("boom")

    orchestrator.register("beta", failing, after=("alpha",), requires={"alpha"})

    with pytest.raises(ModuleExecutionError) as excinfo:
        orchestrator.run()

    error = excinfo.value
    assert error.module == "beta"
    assert "alpha" in error.results
    assert error.results["alpha"].success is True
    assert error.results["beta"].success is False
    assert isinstance(error.cause, RuntimeError)


def test_build_dynamics_reports_overlap_and_queue_metrics() -> None:
    summary = ModuleRunSummary(
        order=("alpha", "beta"),
        context={},
        results={
            "alpha": ModuleRunResult(
                name="alpha",
                success=True,
                duration=0.5,
                output={"alpha": 1},
                error=None,
                ready_at=0.0,
                scheduled_at=0.0,
                started_at=0.0,
                completed_at=0.5,
            ),
            "beta": ModuleRunResult(
                name="beta",
                success=True,
                duration=0.6,
                output={"beta": 2},
                error=None,
                ready_at=0.0,
                scheduled_at=0.1,
                started_at=0.2,
                completed_at=0.8,
            ),
        },
    )

    dynamics = summary.build_dynamics()

    assert dynamics.total_runtime == pytest.approx(0.8)
    assert dynamics.module_runtime_sum == pytest.approx(1.1)
    assert dynamics.peak_concurrency == 2
    assert dynamics.average_concurrency == pytest.approx(1.4666, rel=1e-3)
    assert dynamics.utilisation == pytest.approx(0.7333, rel=1e-3)
    assert dynamics.total_queue_delay == pytest.approx(0.1)
    assert dynamics.average_queue_delay == pytest.approx(0.05)
    assert dynamics.max_queue_delay == pytest.approx(0.1)
    assert len(dynamics.synchronisation) == 2
    assert dynamics.concurrency_profile[1] == pytest.approx(0.5)


def test_build_dynamics_accounts_for_idle_time_before_first_start() -> None:
    summary = ModuleRunSummary(
        order=("alpha", "beta"),
        context={},
        results={
            "alpha": ModuleRunResult(
                name="alpha",
                success=True,
                duration=0.2,
                output={"alpha": 1},
                error=None,
                ready_at=0.0,
                scheduled_at=0.1,
                started_at=0.2,
                completed_at=0.4,
            ),
            "beta": ModuleRunResult(
                name="beta",
                success=True,
                duration=0.4,
                output={"beta": 2},
                error=None,
                ready_at=0.0,
                scheduled_at=0.4,
                started_at=0.5,
                completed_at=0.9,
            ),
        },
    )

    dynamics = summary.build_dynamics()

    assert dynamics.total_runtime == pytest.approx(0.9)
    assert dynamics.total_idle_time == pytest.approx(0.3)
    assert dynamics.concurrency_profile[0] == pytest.approx(0.3)
    assert dynamics.average_concurrency == pytest.approx(2 / 3, rel=1e-3)
    assert dynamics.utilisation == pytest.approx(2 / 3, rel=1e-3)
    assert dynamics.total_queue_delay == pytest.approx(0.5)
    assert dynamics.max_queue_delay == pytest.approx(0.4)


class _StubRiskManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def apply_neural_directive(
        self, *, action: str, alloc_main: float, alloc_alt: float, alloc_scale: float
    ) -> None:
        self.calls.append(
            {
                "action": action,
                "alloc_main": alloc_main,
                "alloc_alt": alloc_alt,
                "alloc_scale": alloc_scale,
            }
        )


def test_apply_neural_decision_normalises_values() -> None:
    manager = _StubRiskManager()
    decision = {
        "action": "rebalance",
        "alloc_main": "0.7",
        "alloc_alt": 0.1,
        "allocs": {"alt": "0.2"},
        "alloc_scale": 1.5,
    }

    apply_neural_decision(decision, manager)

    assert manager.calls == [
        {
            "action": "rebalance",
            "alloc_main": pytest.approx(0.7),
            "alloc_alt": pytest.approx(0.2),
            "alloc_scale": pytest.approx(1.5),
        }
    ]


def test_apply_neural_decision_defaults_none_values() -> None:
    manager = _StubRiskManager()
    decision = {
        "action": "hold",
        "alloc_main": None,
        "alloc_alt": None,
        "allocs": {"main": None},
        "alloc_scale": None,
    }

    apply_neural_decision(decision, manager)

    assert manager.calls == [
        {
            "action": "hold",
            "alloc_main": pytest.approx(0.0),
            "alloc_alt": pytest.approx(0.0),
            "alloc_scale": pytest.approx(1.0),
        }
    ]


def test_apply_neural_decision_rejects_non_numeric_allocations() -> None:
    manager = _StubRiskManager()

    with pytest.raises(
        TypeError, match="Allocation field 'alloc_scale' must be numeric"
    ):
        apply_neural_decision({"alloc_scale": object()}, manager)
