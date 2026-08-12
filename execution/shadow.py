# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shadow deployment controller for live strategy experimentation.

This module implements a traffic mirroring pipeline that evaluates candidate
strategies under live market conditions without impacting the production
decision surface.  The orchestrator receives the market observations consumed by
the incumbent strategy, duplicates them across the configured candidates,
tracks deviations in the resulting signals, and emits deterministic promotion
or rejection decisions based on configurable guardrails.

The implementation favours immutability and dataclass based value objects to
ensure that decisions are auditable and that the entire observation stream can
be archived for forensic analysis.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Mapping, MutableMapping, Protocol

from domain.signal import Signal, SignalAction

__all__ = [
    "ShadowDeploymentConfig",
    "ShadowMetrics",
    "SignalDeviation",
    "ShadowDecision",
    "ShadowArchive",
    "ShadowArchiveRecord",
    "ShadowDeploymentOrchestrator",
]


class SignalGenerator(Protocol):
    """Protocol defining a side-effect free signal generator."""

    def __call__(self, market_state: Mapping[str, Any]) -> Signal:
        """Return a trading :class:`~domain.signal.Signal` for *market_state*."""


class ShadowArchive(Protocol):
    """Persistence backend receiving every shadow observation."""

    def persist(self, record: "ShadowArchiveRecord") -> None:
        """Store *record* for auditability and post-mortem analysis."""


@dataclass(frozen=True, slots=True)
class ShadowDeploymentConfig:
    """Operational parameters governing the shadow deployment pipeline."""

    window_size: int = 300
    min_samples: int = 600
    max_disagreement_rate: float = 0.03
    max_confidence_mape: float = 0.15
    max_action_drift: float = 0.1
    promotion_disagreement_rate: float = 0.01
    promotion_confidence_mape: float = 0.05
    promotion_action_drift: float = 0.05
    promotion_stable_observations: int = 300
    mape_epsilon: float = 1e-3

    def __post_init__(self) -> None:
        if self.window_size <= 0:
            raise ValueError("window_size must be strictly positive")
        if self.min_samples <= 0:
            raise ValueError("min_samples must be strictly positive")
        if self.promotion_stable_observations <= 0:
            raise ValueError("promotion_stable_observations must be positive")
        if not 0.0 <= self.max_disagreement_rate <= 1.0:
            raise ValueError("max_disagreement_rate must be within [0, 1]")
        if not 0.0 <= self.promotion_disagreement_rate <= 1.0:
            raise ValueError("promotion_disagreement_rate must be within [0, 1]")
        if not 0.0 <= self.max_confidence_mape:
            raise ValueError("max_confidence_mape must be non-negative")
        if not 0.0 <= self.promotion_confidence_mape:
            raise ValueError("promotion_confidence_mape must be non-negative")
        if not 0.0 <= self.max_action_drift <= 2.0:
            raise ValueError("max_action_drift must be within [0, 2]")
        if not 0.0 <= self.promotion_action_drift <= 2.0:
            raise ValueError("promotion_action_drift must be within [0, 2]")
        if self.mape_epsilon <= 0.0:
            raise ValueError("mape_epsilon must be strictly positive")


@dataclass(frozen=True, slots=True)
class ShadowMetrics:
    """Rolling deviation metrics over the configured observation window."""

    observations: int
    disagreement_rate: float
    mean_confidence_delta: float
    confidence_mape: float
    action_drift: float


@dataclass(frozen=True, slots=True)
class SignalDeviation:
    """Single tick deviation between baseline and candidate signals."""

    action_mismatch: bool
    confidence_delta: float
    action_delta: float


@dataclass(frozen=True, slots=True)
class ShadowDecision:
    """Decision outcome for a candidate during shadow evaluation."""

    action: str
    reason: str
    metrics: ShadowMetrics


@dataclass(frozen=True, slots=True)
class ShadowArchiveRecord:
    """Materialised observation stored for audit and diagnostics."""

    timestamp: datetime
    candidate: str
    baseline_signal: Signal
    candidate_signal: Signal
    deviation: SignalDeviation
    decision: ShadowDecision


def _action_to_numeric(action: SignalAction | str) -> float:
    resolved = SignalAction(action)
    if resolved is SignalAction.BUY:
        return 1.0
    if resolved is SignalAction.SELL:
        return -1.0
    if resolved is SignalAction.EXIT:
        return 0.0
    return 0.0


@dataclass(slots=True)
class _CandidateState:
    name: str
    generator: SignalGenerator
    config: ShadowDeploymentConfig
    status: str = field(default="active")
    total_observations: int = field(default=0)
    _disagreements: Deque[int] = field(init=False, repr=False)
    _confidence_delta: Deque[float] = field(init=False, repr=False)
    _confidence_mape: Deque[float] = field(init=False, repr=False)
    _baseline_actions: Deque[float] = field(init=False, repr=False)
    _candidate_actions: Deque[float] = field(init=False, repr=False)
    _stable_counter: int = field(default=0, repr=False)
    _latest_metrics: ShadowMetrics | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        maxlen = self.config.window_size
        self._disagreements = deque(maxlen=maxlen)
        self._confidence_delta = deque(maxlen=maxlen)
        self._confidence_mape = deque(maxlen=maxlen)
        self._baseline_actions = deque(maxlen=maxlen)
        self._candidate_actions = deque(maxlen=maxlen)

    def update(self, baseline: Signal, candidate: Signal) -> ShadowMetrics:
        self.total_observations += 1

        disagreement = int(candidate.action != baseline.action)
        self._disagreements.append(disagreement)

        delta = abs(float(candidate.confidence) - float(baseline.confidence))
        self._confidence_delta.append(delta)

        baseline_conf = max(abs(float(baseline.confidence)), self.config.mape_epsilon)
        mape_value = delta / baseline_conf
        self._confidence_mape.append(mape_value)

        self._baseline_actions.append(_action_to_numeric(baseline.action))
        self._candidate_actions.append(_action_to_numeric(candidate.action))

        observations = len(self._disagreements)
        disagreement_rate = sum(self._disagreements) / observations
        mean_conf_delta = sum(self._confidence_delta) / observations
        confidence_mape = sum(self._confidence_mape) / observations
        baseline_mean = sum(self._baseline_actions) / observations
        candidate_mean = sum(self._candidate_actions) / observations
        action_drift = abs(candidate_mean - baseline_mean)

        metrics = ShadowMetrics(
            observations=observations,
            disagreement_rate=disagreement_rate,
            mean_confidence_delta=mean_conf_delta,
            confidence_mape=confidence_mape,
            action_drift=action_drift,
        )

        if (
            disagreement_rate <= self.config.promotion_disagreement_rate
            and confidence_mape <= self.config.promotion_confidence_mape
            and action_drift <= self.config.promotion_action_drift
        ):
            self._stable_counter += 1
        else:
            self._stable_counter = 0

        self._latest_metrics = metrics
        return metrics

    def record_failure(self) -> ShadowMetrics:
        metrics = self._latest_metrics
        if metrics is None:
            metrics = ShadowMetrics(0, 1.0, 0.0, 0.0, 0.0)
        self.status = "rejected"
        return metrics

    def should_reject(self, metrics: ShadowMetrics) -> bool:
        if self.total_observations < self.config.min_samples:
            return False
        if metrics.disagreement_rate > self.config.max_disagreement_rate:
            return True
        if metrics.confidence_mape > self.config.max_confidence_mape:
            return True
        if metrics.action_drift > self.config.max_action_drift:
            return True
        return False

    def should_promote(self, metrics: ShadowMetrics) -> bool:
        if self.total_observations < self.config.min_samples:
            return False
        if self._stable_counter < self.config.promotion_stable_observations:
            return False
        return True


class ShadowDeploymentOrchestrator:
    """Coordinate shadow execution of candidate strategies."""

    def __init__(
        self,
        *,
        baseline: SignalGenerator,
        candidates: Mapping[str, SignalGenerator],
        config: ShadowDeploymentConfig,
        archive: ShadowArchive,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not candidates:
            raise ValueError("at least one candidate strategy must be provided")
        self._baseline = baseline
        self._config = config
        self._archive = archive
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._candidates: MutableMapping[str, _CandidateState] = {}
        for name, generator in candidates.items():
            if not name:
                raise ValueError("candidate name must be provided")
            self._candidates[name] = _CandidateState(name, generator, config)

    def status(self) -> Mapping[str, str]:
        """Return the current lifecycle status for each candidate."""

        return {name: state.status for name, state in self._candidates.items()}

    def process(self, market_state: Mapping[str, Any]) -> Mapping[str, ShadowDecision]:
        """Mirror *market_state* across candidates and evaluate deviations."""

        baseline_signal = self._baseline(market_state)
        decisions: MutableMapping[str, ShadowDecision] = {}

        for name, state in self._candidates.items():
            if state.status != "active":
                metrics = state._latest_metrics or ShadowMetrics(0, 0.0, 0.0, 0.0, 0.0)
                decisions[name] = ShadowDecision(state.status, "terminal", metrics)
                continue

            try:
                candidate_signal = state.generator(market_state)
            except Exception:
                metrics = state.record_failure()
                decision = ShadowDecision("reject", "generator-error", metrics)
                decisions[name] = decision
                record = ShadowArchiveRecord(
                    timestamp=self._clock(),
                    candidate=name,
                    baseline_signal=baseline_signal,
                    candidate_signal=baseline_signal,
                    deviation=SignalDeviation(False, 0.0, 0.0),
                    decision=decision,
                )
                self._archive.persist(record)
                continue

            metrics = state.update(baseline_signal, candidate_signal)
            deviation = SignalDeviation(
                action_mismatch=candidate_signal.action != baseline_signal.action,
                confidence_delta=abs(
                    float(candidate_signal.confidence) - float(baseline_signal.confidence)
                ),
                action_delta=abs(
                    _action_to_numeric(candidate_signal.action)
                    - _action_to_numeric(baseline_signal.action)
                ),
            )

            if state.should_reject(metrics):
                state.status = "rejected"
                decision = ShadowDecision("reject", "guardrail-breach", metrics)
            elif state.should_promote(metrics):
                state.status = "promoted"
                decision = ShadowDecision("promote", "healthy", metrics)
            else:
                decision = ShadowDecision("continue", "monitoring", metrics)

            record = ShadowArchiveRecord(
                timestamp=baseline_signal.timestamp,
                candidate=name,
                baseline_signal=baseline_signal,
                candidate_signal=candidate_signal,
                deviation=deviation,
                decision=decision,
            )
            self._archive.persist(record)
            decisions[name] = decision

        return decisions
