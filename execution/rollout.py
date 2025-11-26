"""Progressive blue/green rollout controller with canary guardrails.

The orchestrator coordinates staged traffic shifting between the incumbent
"blue" deployment and the freshly rolled out "green" deployment. It delegates
traffic management to an injected router, continuously samples live metrics via
the existing :class:`~execution.canary.CanaryController` guardrails, and
triggers an automatic rollback when degradation is detected.

The implementation intentionally keeps all external effects behind protocols so
that production deployments can integrate with load balancers, service meshes
or feature gateways while tests rely on lightweight fakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from time import monotonic, sleep
from typing import Callable, Mapping, Protocol, Sequence

from execution.canary import CanaryController, CanaryDecision

__all__ = [
    "RolloutStep",
    "RolloutAbortedError",
    "TrafficRouter",
    "BlueGreenRolloutOrchestrator",
]


class TrafficRouter(Protocol):
    """Abstract routing primitive for blue/green traffic management."""

    def shift(self, green_share: float) -> None:
        """Route ``green_share`` of the traffic to the green deployment.

        Implementations must ensure ``0.0 <= green_share <= 1.0`` and keep the
        complementary share pinned to the blue deployment. The method is
        expected to be idempotent and transactional – if the underlying call
        fails, an exception should be raised and no partial state should leak.
        """

    def rollback(self, previous_green_share: float) -> None:
        """Revert the routing configuration to ``previous_green_share``."""

    def promote(self) -> None:
        """Finalize the rollout by making the green deployment the new blue."""


@dataclass(frozen=True)
class RolloutStep:
    """Single progressive traffic increment for the rollout."""

    green_share: float
    min_duration: float
    max_duration: float | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.green_share <= 1.0:
            raise ValueError("green_share must be between 0.0 and 1.0 inclusive")
        if self.min_duration <= 0.0:
            raise ValueError("min_duration must be strictly positive")
        if self.max_duration is not None:
            if self.max_duration <= 0.0:
                raise ValueError("max_duration must be positive when provided")
            if self.max_duration < self.min_duration:
                raise ValueError("max_duration cannot be less than min_duration")


class RolloutAbortedError(RuntimeError):
    """Raised when the rollout is aborted because guardrails tripped."""

    def __init__(
        self,
        *,
        reason: str,
        decision: CanaryDecision,
        metrics: Mapping[str, float],
    ) -> None:
        super().__init__(f"Rollout aborted: {reason}")
        self.reason = reason
        self.decision = decision
        self.metrics = dict(metrics)


RollbackCallback = Callable[[str, Mapping[str, float], CanaryDecision], None]


class BlueGreenRolloutOrchestrator:
    """Coordinate blue/green or canary rollouts with automated guardrails."""

    def __init__(
        self,
        steps: Sequence[RolloutStep],
        *,
        router: TrafficRouter,
        canary_controller: CanaryController,
        metrics_provider: Callable[[], Mapping[str, float]],
        rollback_callback: RollbackCallback | None = None,
        poll_interval: float = 15.0,
        time_source: Callable[[], float] = monotonic,
        sleep_fn: Callable[[float], None] = sleep,
    ) -> None:
        if not steps:
            raise ValueError("steps must not be empty")
        if poll_interval <= 0.0:
            raise ValueError("poll_interval must be strictly positive")

        ordered = sorted(step.green_share for step in steps)
        if ordered != [step.green_share for step in steps]:
            raise ValueError("steps must be ordered by non-decreasing green_share")
        if steps[-1].green_share < 1.0:
            raise ValueError("final rollout step must route 100% traffic to green")

        self._steps = list(steps)
        self._router = router
        self._controller = canary_controller
        self._metrics_provider = metrics_provider
        self._rollback_callback = rollback_callback
        self._poll_interval = poll_interval
        self._time = time_source
        self._sleep = sleep_fn

    def execute(self) -> None:
        """Run the configured rollout plan.

        Raises :class:`RolloutAbortedError` when a guardrail breach is detected
        and the orchestrator performs an automatic rollback.
        """

        self._controller.reset()
        previous_share = 0.0
        try:
            for step in self._steps:
                self._router.shift(step.green_share)
                self._monitor_step(step, previous_share)
                previous_share = step.green_share
            self._router.promote()
        finally:
            self._controller.reset()

    def _monitor_step(self, step: RolloutStep, previous_share: float) -> None:
        start = self._time()
        deadline = start + step.max_duration if step.max_duration is not None else None

        while True:
            metrics = self._metrics_provider()
            decision = self._controller.evaluate(metrics)
            if decision.action != "continue" or decision.breaches:
                self._handle_failure(previous_share, decision, metrics)

            now = self._time()
            if deadline is not None and now >= deadline:
                timeout_decision = CanaryDecision("disable", "step-timeout", {})
                self._handle_failure(previous_share, timeout_decision, metrics)

            if now - start >= step.min_duration:
                return

            next_sleep = self._poll_interval
            remaining_min = step.min_duration - (now - start)
            if remaining_min < next_sleep:
                next_sleep = remaining_min
            if deadline is not None:
                remaining_deadline = deadline - now
                if remaining_deadline <= 0.0:
                    timeout_decision = CanaryDecision("disable", "step-timeout", {})
                    self._handle_failure(previous_share, timeout_decision, metrics)
                if remaining_deadline < next_sleep:
                    next_sleep = remaining_deadline

            if next_sleep > 0.0 and isfinite(next_sleep):
                self._sleep(next_sleep)

    def _handle_failure(
        self,
        previous_share: float,
        decision: CanaryDecision,
        metrics: Mapping[str, float],
    ) -> None:
        self._router.rollback(previous_share)
        if self._rollback_callback is not None:
            self._rollback_callback(decision.reason, metrics, decision)
        self._controller.reset()
        raise RolloutAbortedError(
            reason=decision.reason, decision=decision, metrics=metrics
        )
