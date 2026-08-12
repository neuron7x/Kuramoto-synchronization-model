# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import time
from concurrent.futures import CancelledError
from typing import Any, Sequence

import pytest

from core.agent.evaluator import EvaluationResult
from core.agent.orchestrator import (
    StrategyFlow,
    StrategyOrchestrationError,
    StrategyOrchestrator,
)
from core.agent.strategy import Strategy


class RecordingEvaluator:
    def __init__(
        self,
        calls: list[tuple[tuple[str, ...], Any, bool]],
        *,
        delay: float = 0.0,
        fail_on: set[Any] | None = None,
    ) -> None:
        self._calls = calls
        self._delay = delay
        self._fail_on = set() if fail_on is None else set(fail_on)

    def evaluate(
        self,
        strategies: Sequence[Strategy],
        data: Any,
        *,
        raise_on_error: bool = False,
    ) -> list[EvaluationResult]:
        names = tuple(strategy.name for strategy in strategies)
        self._calls.append((names, data, raise_on_error))
        if self._delay:
            time.sleep(self._delay)
        if data in self._fail_on:
            raise RuntimeError(f"flow {data} failed")
        results: list[EvaluationResult] = []
        for strategy in strategies:
            results.append(
                EvaluationResult(
                    strategy=strategy,
                    score=1.0,
                    duration=self._delay,
                    error=None,
                )
            )
        return results


def _make_strategy(name: str) -> Strategy:
    return Strategy(name=name, params={"lookback": 5, "threshold": 0.1})


def test_orchestrator_runs_flows_in_parallel() -> None:
    calls: list[tuple[tuple[str, ...], Any, bool]] = []
    orchestrator = StrategyOrchestrator(
        max_parallel=2,
        evaluator_factory=lambda: RecordingEvaluator(calls, delay=0.2),
    )
    flows = [
        StrategyFlow(name="alpha", strategies=[_make_strategy("s1")], dataset="alpha"),
        StrategyFlow(name="beta", strategies=[_make_strategy("s2")], dataset="beta"),
    ]

    start = time.perf_counter()
    orchestrator.run_flows(flows)
    duration = time.perf_counter() - start
    orchestrator.shutdown()

    assert duration < 0.35
    assert {names[0] for names, *_ in calls} == {"s1", "s2"}


def test_orchestrator_prevents_conflicting_flows() -> None:
    orchestrator = StrategyOrchestrator(
        max_parallel=1,
        evaluator_factory=lambda: RecordingEvaluator([], delay=0.05),
    )
    flow = StrategyFlow(name="alpha", strategies=[_make_strategy("s1")], dataset="alpha")

    future = orchestrator.submit_flow(flow)
    with pytest.raises(RuntimeError):
        orchestrator.submit_flow(flow)

    future.result()
    orchestrator.submit_flow(flow).result()
    orchestrator.shutdown()


def test_orchestrator_collects_results_and_flags_raise_on_error() -> None:
    calls: list[tuple[tuple[str, ...], Any, bool]] = []
    orchestrator = StrategyOrchestrator(
        max_parallel=3,
        evaluator_factory=lambda: RecordingEvaluator(calls),
    )
    flows = [
        StrategyFlow(name="alpha", strategies=[_make_strategy("s1")], dataset="payload"),
        StrategyFlow(
            name="beta",
            strategies=[_make_strategy("s2")],
            dataset="payload",
            raise_on_error=True,
        ),
    ]

    results = orchestrator.run_flows(flows)
    orchestrator.shutdown()

    assert set(results.keys()) == {"alpha", "beta"}
    assert all(isinstance(res[0], EvaluationResult) for res in results.values())

    call_map = {names[0]: (data, flag) for names, data, flag in calls}
    assert call_map["s1"] == ("payload", False)
    assert call_map["s2"] == ("payload", True)


def test_orchestrator_surfaces_flow_errors_with_context() -> None:
    calls: list[tuple[tuple[str, ...], Any, bool]] = []
    orchestrator = StrategyOrchestrator(
        max_parallel=2,
        evaluator_factory=lambda: RecordingEvaluator(calls, fail_on={"bad"}),
    )
    flows = [
        StrategyFlow(name="good", strategies=[_make_strategy("s1")], dataset="ok"),
        StrategyFlow(name="bad", strategies=[_make_strategy("s2")], dataset="bad"),
    ]

    with pytest.raises(StrategyOrchestrationError) as excinfo:
        orchestrator.run_flows(flows)

    orchestrator.shutdown()

    error = excinfo.value
    assert set(error.errors.keys()) == {"bad"}
    assert "flow bad failed" in str(error)
    assert "good" in error.results
    assert isinstance(error.results["good"][0], EvaluationResult)


def test_orchestrator_cancels_pending_flows_after_failure() -> None:
    calls: list[tuple[tuple[str, ...], Any, bool]] = []
    orchestrator = StrategyOrchestrator(
        max_parallel=1,
        max_queue_size=5,
        evaluator_factory=lambda: RecordingEvaluator(calls, delay=0.2, fail_on={"fail"}),
    )

    flows = [
        StrategyFlow(name="fail", strategies=[_make_strategy("f")], dataset="fail"),
        StrategyFlow(
            name="queued-1",
            strategies=[_make_strategy("q1")],
            dataset="queued-1",
        ),
        StrategyFlow(
            name="queued-2",
            strategies=[_make_strategy("q2")],
            dataset="queued-2",
        ),
    ]

    with pytest.raises(StrategyOrchestrationError) as excinfo:
        orchestrator.run_flows(flows)

    orchestrator.shutdown()

    error = excinfo.value
    assert isinstance(error.errors.get("fail"), RuntimeError)
    assert isinstance(error.errors.get("queued-2"), CancelledError)
    assert "queued-1" in error.results
    assert [names[0] for names, *_ in calls] == ["f", "q1"]


def test_orchestrator_prioritizes_queues() -> None:
    calls: list[tuple[tuple[str, ...], Any, bool]] = []
    orchestrator = StrategyOrchestrator(
        max_parallel=1,
        evaluator_factory=lambda: RecordingEvaluator(calls, delay=0.05),
    )

    blocker = StrategyFlow(
        name="blocker",
        strategies=[_make_strategy("blocker")],
        dataset="blocker",
        priority=0,
    )
    low = StrategyFlow(
        name="low",
        strategies=[_make_strategy("low")],
        dataset="low",
        priority=5,
    )
    high = StrategyFlow(
        name="high",
        strategies=[_make_strategy("high")],
        dataset="high",
        priority=-5,
    )

    future_blocker = orchestrator.submit_flow(blocker)
    future_low = orchestrator.submit_flow(low)
    future_high = orchestrator.submit_flow(high)

    future_blocker.result()
    future_high.result()
    future_low.result()
    orchestrator.shutdown()

    observed = [data for (_, data, _) in calls if data != "blocker"]
    assert observed == ["high", "low"]


def test_orchestrator_applies_backpressure() -> None:
    calls: list[tuple[tuple[str, ...], Any, bool]] = []
    orchestrator = StrategyOrchestrator(
        max_parallel=1,
        max_queue_size=1,
        evaluator_factory=lambda: RecordingEvaluator(calls, delay=0.2),
    )

    first = StrategyFlow(
        name="first",
        strategies=[_make_strategy("first")],
        dataset="first",
    )
    second = StrategyFlow(
        name="second",
        strategies=[_make_strategy("second")],
        dataset="second",
    )
    third = StrategyFlow(
        name="third",
        strategies=[_make_strategy("third")],
        dataset="third",
    )

    orchestrator.submit_flow(first)
    orchestrator.submit_flow(second)
    with pytest.raises(TimeoutError):
        orchestrator.submit_flow(third, timeout=0.05)

    orchestrator.shutdown(cancel_pending=True)


def test_orchestrator_isolates_evaluator_state() -> None:
    created: list[int] = []

    class StatefulEvaluator:
        def __init__(self) -> None:
            self.counter = 0
            created.append(id(self))

        def evaluate(
            self,
            strategies: Sequence[Strategy],
            data: Any,
            *,
            raise_on_error: bool = False,
        ) -> list[EvaluationResult]:
            self.counter += 1
            return [
                EvaluationResult(strategy=strategy, score=1.0, duration=0.0, error=None)
                for strategy in strategies
            ]

    orchestrator = StrategyOrchestrator(
        max_parallel=2,
        evaluator_factory=StatefulEvaluator,
    )

    flows = [
        StrategyFlow(name=f"flow-{idx}", strategies=[_make_strategy(f"s{idx}")], dataset=idx)
        for idx in range(3)
    ]

    orchestrator.run_flows(flows)
    orchestrator.shutdown()

    assert len(created) == len(flows)


def test_orchestrator_shutdown_cancels_pending_flows() -> None:
    calls: list[tuple[tuple[str, ...], Any, bool]] = []
    orchestrator = StrategyOrchestrator(
        max_parallel=1,
        max_queue_size=2,
        evaluator_factory=lambda: RecordingEvaluator(calls, delay=0.2),
    )

    active_flow = StrategyFlow(
        name="active",
        strategies=[_make_strategy("active")],
        dataset="active",
    )
    pending_flow = StrategyFlow(
        name="pending",
        strategies=[_make_strategy("pending")],
        dataset="pending",
    )

    running = orchestrator.submit_flow(active_flow)
    queued = orchestrator.submit_flow(pending_flow)

    for _ in range(50):
        if "active" in orchestrator.active_flows():
            break
        time.sleep(0.01)

    orchestrator.shutdown(cancel_pending=True)

    assert running.result()[0].strategy.name == "active"
    with pytest.raises(CancelledError):
        queued.result()

    with pytest.raises(RuntimeError):
        orchestrator.submit_flow(
            StrategyFlow(
                name="after",
                strategies=[_make_strategy("after")],
                dataset="after",
            )
        )
