"""Mode orchestration state machine with hysteresis.

The orchestrator coordinates trading modes between *Action*, *Cooldown*,
*Rest*, and *Safe-Exit*.  The design follows three guiding principles:

1.  **Determinism** – transitions depend solely on the most recent metrics
    snapshot and elapsed durations tracked in the orchestrator, which makes
    the behaviour reproducible and friendly to property testing.
2.  **Hysteresis** – thresholds include recovery bands to prevent rapid
    oscillations when a guard condition hovers around the decision boundary.
3.  **Latency guarantees** – transitions are performed synchronously during
    the update call, ensuring sub-millisecond runtime cost so long as the
    caller provides monotonic timestamps.

The implementation is deliberately free from threading primitives so it can
run identically in high-frequency Python loops or be ported to the Rust
runtime (see ``core/orchestrator/mode_orchestrator.rs``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class ModeState(str, Enum):
    """Enumerates the supported orchestrator modes."""

    ACTION = "action"
    COOLDOWN = "cooldown"
    REST = "rest"
    SAFE_EXIT = "safe_exit"


@dataclass(frozen=True)
class GuardBand:
    """Hysteresis-aware guard band for a monitored signal.

    Attributes
    ----------
    soft_limit:
        Breach of this limit triggers a defensive transition (e.g. Action →
        Cooldown).
    hard_limit:
        Breach of this limit forces an immediate Safe-Exit transition.
    recover_limit:
        Returning below this limit indicates the system has recovered and can
        resume a more aggressive mode after dwell timers expire.
    """

    soft_limit: float
    hard_limit: float
    recover_limit: float

    def __post_init__(self) -> None:  # pragma: no cover - validated indirectly
        if not self.recover_limit <= self.soft_limit <= self.hard_limit:
            raise ValueError(
                "GuardBand expects recover_limit ≤ soft_limit ≤ hard_limit",
            )

    def is_soft_breach(self, value: float) -> bool:
        return value >= self.soft_limit

    def is_hard_breach(self, value: float) -> bool:
        return value >= self.hard_limit

    def is_recovered(self, value: float) -> bool:
        return value <= self.recover_limit


@dataclass(frozen=True)
class GuardConfig:
    """Collection of guard bands for all monitored risk indicators."""

    kappa: GuardBand
    var: GuardBand
    max_drawdown: GuardBand
    heat: GuardBand


@dataclass(frozen=True)
class TimeoutConfig:
    """Configurable dwell times for each mode."""

    action_max: float
    cooldown_min: float
    rest_min: float
    cooldown_persistence: float
    safe_exit_lock: float


@dataclass(frozen=True)
class DelayBudget:
    """Permissible detection→transition latencies for each path."""

    action_to_cooldown: float
    cooldown_to_rest: float
    protective_to_safe_exit: float


@dataclass(frozen=True)
class MetricsSnapshot:
    """Real-time snapshot of orchestrator inputs."""

    kappa: float
    var: float
    max_drawdown: float
    heat: float


@dataclass
class ModeOrchestratorConfig:
    """Container bundling guard, timeout, and delay policies."""

    guards: GuardConfig
    timeouts: TimeoutConfig
    delays: DelayBudget
    initial_state: ModeState = ModeState.REST


@dataclass
class ModeOrchestrator:
    """Finite-state mode orchestrator with hysteresis."""

    config: ModeOrchestratorConfig
    _state: ModeState = field(init=False)
    _state_entered_at: Optional[float] = field(default=None, init=False)
    _last_timestamp: Optional[float] = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._state = self.config.initial_state

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def state(self) -> ModeState:
        return self._state

    def reset(
        self, state: Optional[ModeState] = None, *, timestamp: float = 0.0
    ) -> None:
        """Reinitialise the orchestrator for deterministic testing."""

        self._state = state or self.config.initial_state
        self._state_entered_at = timestamp
        self._last_timestamp = timestamp

    def snapshot(self) -> Dict[str, float | str]:
        """Provide a debug-friendly snapshot of the orchestrator."""

        return {
            "state": self._state.value,
            "state_entered_at": self._state_entered_at,
            "last_timestamp": self._last_timestamp,
        }

    # ------------------------------------------------------------------
    # Core update logic
    # ------------------------------------------------------------------
    def update(self, metrics: MetricsSnapshot, timestamp: float) -> ModeState:
        """Advance the orchestrator using the supplied metrics.

        Parameters
        ----------
        metrics:
            Latest telemetry snapshot.
        timestamp:
            Monotonic timestamp in seconds.  The caller is responsible for
            providing non-decreasing values.
        """

        self._validate_timestamp(timestamp)

        if self._state_entered_at is None:
            self._state_entered_at = timestamp

        guard = self.config.guards

        hard_breach = self._any_guard(metrics, guard, "is_hard_breach")
        soft_breach = self._any_guard(metrics, guard, "is_soft_breach")
        recovered = self._all_guard(metrics, guard, "is_recovered")
        state_started = (
            self._state_entered_at if self._state_entered_at is not None else timestamp
        )
        elapsed = timestamp - state_started

        if hard_breach:
            return self._transition_to_safe_exit(timestamp)

        if self._state == ModeState.ACTION:
            if soft_breach:
                return self._transition_if_within_budget(
                    ModeState.COOLDOWN,
                    timestamp,
                    self.config.delays.action_to_cooldown,
                )
            if elapsed >= self.config.timeouts.action_max:
                return self._transition_if_within_budget(
                    ModeState.COOLDOWN,
                    timestamp,
                    self.config.delays.action_to_cooldown,
                )
            return self._state

        if self._state == ModeState.COOLDOWN:
            if recovered and elapsed >= self.config.timeouts.cooldown_min:
                return self._transition(ModeState.ACTION, timestamp)
            if not recovered and elapsed >= self.config.timeouts.cooldown_persistence:
                return self._transition_if_within_budget(
                    ModeState.REST,
                    timestamp,
                    self.config.delays.cooldown_to_rest,
                )
            return self._state

        if self._state == ModeState.REST:
            if recovered and elapsed >= self.config.timeouts.rest_min:
                return self._transition(ModeState.ACTION, timestamp)
            return self._state

        if self._state == ModeState.SAFE_EXIT:
            state_started = (
                self._state_entered_at
                if self._state_entered_at is not None
                else timestamp
            )
            lock_elapsed = timestamp - state_started
            if lock_elapsed >= self.config.timeouts.safe_exit_lock and recovered:
                return self._transition(ModeState.REST, timestamp)
            return self._state

        raise RuntimeError(f"Unsupported state: {self._state}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _transition(self, new_state: ModeState, timestamp: float) -> ModeState:
        if new_state == self._state:
            return self._state
        self._state = new_state
        self._state_entered_at = timestamp
        self._last_timestamp = timestamp
        return self._state

    def _transition_if_within_budget(
        self,
        new_state: ModeState,
        timestamp: float,
        budget: float,
    ) -> ModeState:
        if budget < 0:
            raise ValueError("Delay budget cannot be negative")
        # Transitions are immediate, guaranteeing latency <= budget.
        return self._transition(new_state, timestamp)

    def _transition_to_safe_exit(self, timestamp: float) -> ModeState:
        return self._transition_if_within_budget(
            ModeState.SAFE_EXIT,
            timestamp,
            self.config.delays.protective_to_safe_exit,
        )

    def _validate_timestamp(self, timestamp: float) -> None:
        if self._last_timestamp is not None and timestamp < self._last_timestamp:
            raise ValueError("Timestamp regression detected in orchestrator")
        self._last_timestamp = timestamp

    @staticmethod
    def _any_guard(metrics: MetricsSnapshot, guards: GuardConfig, method: str) -> bool:
        return any(
            getattr(band, method)(value)
            for band, value in zip(
                (guards.kappa, guards.var, guards.max_drawdown, guards.heat),
                (metrics.kappa, metrics.var, metrics.max_drawdown, metrics.heat),
            )
        )

    @staticmethod
    def _all_guard(metrics: MetricsSnapshot, guards: GuardConfig, method: str) -> bool:
        return all(
            getattr(band, method)(value)
            for band, value in zip(
                (guards.kappa, guards.var, guards.max_drawdown, guards.heat),
                (metrics.kappa, metrics.var, metrics.max_drawdown, metrics.heat),
            )
        )
