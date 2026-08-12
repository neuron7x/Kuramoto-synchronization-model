# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from typing import Mapping

import pytest

from execution.canary import CanaryDecision
from execution.rollout import (
    BlueGreenRolloutOrchestrator,
    RolloutAbortedError,
    RolloutStep,
)


class _FakeRouter:
    def __init__(self) -> None:
        self.shifts: list[float] = []
        self.rollback_calls: list[float] = []
        self.promoted = False

    def shift(self, green_share: float) -> None:
        self.shifts.append(green_share)

    def rollback(self, previous_green_share: float) -> None:
        self.rollback_calls.append(previous_green_share)

    def promote(self) -> None:
        self.promoted = True


class _StubCanaryController:
    def __init__(self, decisions: list[CanaryDecision]) -> None:
        self._decisions = decisions
        self.reset_calls = 0

    def evaluate(self, metrics: Mapping[str, float]) -> CanaryDecision:
        if self._decisions:
            return self._decisions.pop(0)
        return CanaryDecision("continue", "healthy", {})

    def reset(self) -> None:
        self.reset_calls += 1


class _FakeClock:
    def __init__(self) -> None:
        self._now = 0.0

    def now(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._now += seconds


def test_rollout_successfully_promotes_green() -> None:
    steps = [
        RolloutStep(green_share=0.1, min_duration=5.0),
        RolloutStep(green_share=0.5, min_duration=5.0),
        RolloutStep(green_share=1.0, min_duration=5.0),
    ]
    router = _FakeRouter()
    controller = _StubCanaryController(
        [CanaryDecision("continue", "healthy", {}) for _ in range(10)]
    )
    clock = _FakeClock()

    orchestrator = BlueGreenRolloutOrchestrator(
        steps,
        router=router,
        canary_controller=controller,
        metrics_provider=lambda: {"pnl": 1.0, "latency_p95": 120.0},
        poll_interval=5.0,
        time_source=clock.now,
        sleep_fn=clock.sleep,
    )

    orchestrator.execute()

    assert router.shifts == [0.1, 0.5, 1.0]
    assert router.rollback_calls == []
    assert router.promoted is True
    assert controller.reset_calls == 2


def test_rollout_aborts_and_rolls_back_on_guardrail_breach() -> None:
    steps = [
        RolloutStep(green_share=0.2, min_duration=5.0),
        RolloutStep(green_share=1.0, min_duration=5.0),
    ]
    router = _FakeRouter()
    controller = _StubCanaryController(
        [
            CanaryDecision("continue", "healthy", {}),
            CanaryDecision("continue", "healthy", {}),
            CanaryDecision("disable", "guardrail-breach", {"latency_p95": 25.0}),
        ]
    )
    clock = _FakeClock()
    metrics_snapshot = {"pnl": 0.95, "latency_p95": 25.0}
    rollback_events: list[tuple[str, dict[str, float], CanaryDecision]] = []

    def record_rollback(reason: str, metrics: dict[str, float], decision: CanaryDecision) -> None:
        rollback_events.append((reason, dict(metrics), decision))

    orchestrator = BlueGreenRolloutOrchestrator(
        steps,
        router=router,
        canary_controller=controller,
        metrics_provider=lambda: metrics_snapshot,
        rollback_callback=record_rollback,
        poll_interval=5.0,
        time_source=clock.now,
        sleep_fn=clock.sleep,
    )

    with pytest.raises(RolloutAbortedError) as excinfo:
        orchestrator.execute()

    assert router.shifts == [0.2, 1.0]
    assert router.rollback_calls == [0.2]
    assert router.promoted is False
    assert controller.reset_calls == 3
    assert excinfo.value.reason == "guardrail-breach"
    assert excinfo.value.decision.breaches == {"latency_p95": 25.0}
    assert excinfo.value.metrics == metrics_snapshot
    assert rollback_events == [
        (
            "guardrail-breach",
            metrics_snapshot,
            CanaryDecision("disable", "guardrail-breach", {"latency_p95": 25.0}),
        )
    ]


def test_rollout_treats_cooldown_with_breaches_as_failure() -> None:
    steps = [
        RolloutStep(green_share=0.4, min_duration=5.0),
        RolloutStep(green_share=1.0, min_duration=5.0),
    ]
    router = _FakeRouter()
    controller = _StubCanaryController(
        [
            CanaryDecision("continue", "healthy", {}),
            CanaryDecision("continue", "healthy", {}),
            CanaryDecision("continue", "cooldown", {"error_rate": 0.02}),
        ]
    )
    clock = _FakeClock()

    orchestrator = BlueGreenRolloutOrchestrator(
        steps,
        router=router,
        canary_controller=controller,
        metrics_provider=lambda: {"pnl": 1.0, "error_rate": 0.02},
        poll_interval=5.0,
        time_source=clock.now,
        sleep_fn=clock.sleep,
    )

    with pytest.raises(RolloutAbortedError) as excinfo:
        orchestrator.execute()

    assert excinfo.value.reason == "cooldown"
    assert router.rollback_calls == [0.4]


def test_rollout_requires_monotonic_steps() -> None:
    with pytest.raises(ValueError, match="non-decreasing"):
        BlueGreenRolloutOrchestrator(
            [
                RolloutStep(green_share=0.6, min_duration=5.0),
                RolloutStep(green_share=0.2, min_duration=5.0),
                RolloutStep(green_share=1.0, min_duration=5.0),
            ],
            router=_FakeRouter(),
            canary_controller=_StubCanaryController([]),
            metrics_provider=lambda: {},
        )

    with pytest.raises(ValueError, match="100% traffic"):
        BlueGreenRolloutOrchestrator(
            [RolloutStep(green_share=0.9, min_duration=5.0)],
            router=_FakeRouter(),
            canary_controller=_StubCanaryController([]),
            metrics_provider=lambda: {},
        )
