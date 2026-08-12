from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from math import isfinite
from numbers import Real
from threading import RLock
from types import MappingProxyType
from typing import Callable, Mapping

from geosync.core.compat import default_clock


def utc_now() -> datetime:
    """Tz-aware UTC ``datetime`` from the injected :class:`Clock`.

    Routes through ``default_clock().now()`` so audit events and phase
    transitions are deterministic under a ``FrozenClock`` (Class A migration —
    formal/micro_dynamic_bug_fractal_audit.md §3, replay determinism invariant).
    """

    return default_clock().now()


class ExplorationPhase(str, Enum):
    INACTIVE = "inactive"
    ATTENUATION = "attenuation"
    DESEGREGATION = "desegregation"
    DIVERSITY = "diversity"
    REINTEGRATION = "reintegration"


class ReintegrationOutcome(str, Enum):
    NOT_RUN = "not_run"
    SUCCESS = "success"
    FAILED = "failed"
    EMERGENCY_EXIT = "emergency_exit"


@dataclass(frozen=True)
class EntropyBudget:
    max_entropy: float = 0.35
    current_entropy: float = 0.0
    peak_entropy: float = 0.0

    def within_budget(self) -> bool:
        return 0.0 <= self.current_entropy <= self.max_entropy


@dataclass(frozen=True)
class RebusConfig:
    attenuation_factor: float = 0.4
    max_duration_bars: int = 20
    diversity_multiplier: float = 1.6
    activation_coherence_threshold: float = 0.80
    reintegration_coherence_threshold: float = 0.75
    max_cross_module_openings: int = 1
    max_audit_events: int = 256


@dataclass(frozen=True)
class ExplorationControl:
    attenuation_factor: float
    cross_module_openings: int
    diversity_gain: float


@dataclass(frozen=True)
class RebusSnapshot:
    phase: ExplorationPhase
    activated_at: datetime | None
    bars_elapsed: int
    entropy_budget: EntropyBudget
    forced_halt_reason: str | None
    reintegration_coherence: float
    reintegration_outcome: ReintegrationOutcome
    cycle_id: str | None
    is_active: bool
    control: ExplorationControl


@dataclass(frozen=True)
class RebusAuditEvent:
    ts: datetime
    event: str
    cycle_id: str | None
    phase: ExplorationPhase
    bars_elapsed: int
    details: Mapping[str, object]


class ExplorationContractError(RuntimeError):
    """Raised when exploration contract or invariants are violated."""


class RebusGate:
    def __init__(self, config: RebusConfig | None = None) -> None:
        self._lock = RLock()
        self._config = config or RebusConfig()
        self._validate_config(self._config)

        self._phase = ExplorationPhase.INACTIVE
        self._activated_at: datetime | None = None
        self._bars_elapsed = 0
        self._entropy_budget = EntropyBudget()
        self._forced_halt_reason: str | None = None
        self._reintegration_coherence = 0.0
        self._reintegration_outcome = ReintegrationOutcome.NOT_RUN
        self._cycle_id: str | None = None
        self._prior_weights_backup: dict[str, float] | None = None
        self._restore_callback: Callable[[Mapping[str, float]], bool] | None = None
        self._audit_log: deque[RebusAuditEvent] = deque(maxlen=self._config.max_audit_events)
        self._cross_module_openings = 0
        self._diversity_gain = 1.0

    def snapshot(self) -> RebusSnapshot:
        with self._lock:
            return RebusSnapshot(
                phase=self._phase,
                activated_at=self._activated_at,
                bars_elapsed=self._bars_elapsed,
                entropy_budget=self._entropy_budget,
                forced_halt_reason=self._forced_halt_reason,
                reintegration_coherence=self._reintegration_coherence,
                reintegration_outcome=self._reintegration_outcome,
                cycle_id=self._cycle_id,
                is_active=self.is_active(),
                control=self.control_vector(),
            )

    def control_vector(self) -> ExplorationControl:
        with self._lock:
            attenuation = (
                self._config.attenuation_factor
                if self._phase
                in {
                    ExplorationPhase.ATTENUATION,
                    ExplorationPhase.DESEGREGATION,
                    ExplorationPhase.DIVERSITY,
                }
                else 1.0
            )
            return ExplorationControl(
                attenuation_factor=attenuation,
                cross_module_openings=self._cross_module_openings,
                diversity_gain=self._diversity_gain,
            )

    def can_activate(self, parent_nominal: bool, current_coherence: float) -> bool:
        with self._lock:
            coherence_value = self._require_finite_real(
                name="current_coherence",
                value=current_coherence,
                message="activation denied: coherence must be a finite real number",
            )
            return (
                parent_nominal
                and self._phase == ExplorationPhase.INACTIVE
                and self._prior_weights_backup is None
                and coherence_value >= self._config.activation_coherence_threshold
            )

    def activate(
        self,
        cycle_id: str,
        prior_weights: Mapping[str, float],
        *,
        parent_nominal: bool,
        current_coherence: float,
        apply_attenuated_priors: Callable[[Mapping[str, float]], bool],
        apply_restored_priors: Callable[[Mapping[str, float]], bool],
    ) -> dict[str, float]:
        with self._lock:
            if not self.can_activate(parent_nominal, current_coherence):
                raise ExplorationContractError(
                    "activation denied: parent must be NOMINAL and coherence at baseline"
                )
            if not cycle_id:
                raise ExplorationContractError("activation denied: cycle_id is required")
            if not isinstance(prior_weights, Mapping):
                raise ExplorationContractError(
                    "activation denied: prior_weights must be a mapping of finite real values"
                )
            if not prior_weights:
                raise ExplorationContractError("activation denied: prior_weights must not be empty")
            if not callable(apply_attenuated_priors):
                raise ExplorationContractError(
                    "activation denied: apply_attenuated_priors callback is required"
                )
            if not callable(apply_restored_priors):
                raise ExplorationContractError(
                    "activation denied: apply_restored_priors callback is required"
                )

            attenuated: dict[str, float] = {}
            try:
                prior_pairs = tuple(prior_weights.items())
            except Exception as exc:
                raise ExplorationContractError(
                    "activation denied: prior_weights mapping could not be read"
                ) from exc
            try:
                for key, value in prior_pairs:
                    finite_value = self._require_finite_real(
                        name=f"prior_weights[{key!r}]",
                        value=value,
                        message=f"activation denied: prior value for key={key!r} must be a finite real number",
                    )
                    attenuated[key] = finite_value * self._config.attenuation_factor
            except (TypeError, ValueError) as exc:
                raise ExplorationContractError(
                    "activation denied: prior_weights entries must be key/value pairs"
                ) from exc

            self._apply_callback_or_raise(
                apply_attenuated_priors,
                attenuated,
                failure_event="activation_apply_failed",
                failure_reason="attenuated_apply_failed",
            )

            self._prior_weights_backup = dict(prior_weights)
            self._restore_callback = apply_restored_priors
            self._phase = ExplorationPhase.ATTENUATION
            self._activated_at = utc_now()
            self._bars_elapsed = 0
            self._entropy_budget = EntropyBudget(max_entropy=self._entropy_budget.max_entropy)
            self._forced_halt_reason = None
            self._reintegration_coherence = 0.0
            self._reintegration_outcome = ReintegrationOutcome.NOT_RUN
            self._cycle_id = cycle_id
            self._cross_module_openings = 0
            self._diversity_gain = 1.0
            self._append_event(
                "activated",
                {
                    "attenuated_keys": len(attenuated),
                    "coherence": current_coherence,
                    "entropy": self._entropy_budget.current_entropy,
                    "peak_entropy": self._entropy_budget.peak_entropy,
                    "cross_module_openings": self._cross_module_openings,
                },
            )
            return attenuated

    def step(self, current_entropy: float, coherence: float) -> ExplorationPhase:
        with self._lock:
            if self._phase == ExplorationPhase.INACTIVE:
                raise ExplorationContractError("step denied: gate is inactive")
            if self._phase == ExplorationPhase.REINTEGRATION:
                raise ExplorationContractError(
                    "step denied: reintegration pending; call reintegrate() or emergency_exit()"
                )
            entropy_value = self._require_finite_real(
                name="current_entropy",
                value=current_entropy,
                message="step denied: entropy must be a finite real number",
            )
            coherence_value = self._require_finite_real(
                name="coherence",
                value=coherence,
                message="step denied: coherence must be a finite real number",
            )

            self._bars_elapsed += 1
            peak_entropy = max(self._entropy_budget.peak_entropy, entropy_value)
            self._entropy_budget = replace(
                self._entropy_budget,
                current_entropy=entropy_value,
                peak_entropy=peak_entropy,
            )

            prev_phase = self._phase
            forced_reason: str | None = None

            if coherence_value < self._config.reintegration_coherence_threshold:
                forced_reason = "coherence_below_reintegration_threshold"
            elif entropy_value > self._entropy_budget.max_entropy:
                forced_reason = "entropy_ceiling_exceeded"
            elif self._bars_elapsed >= self._config.max_duration_bars:
                forced_reason = "max_duration_reached"

            if forced_reason is not None:
                self._phase = ExplorationPhase.REINTEGRATION
                self._forced_halt_reason = forced_reason
                self._diversity_gain = 1.0
                self._append_event(
                    "forced_reintegration",
                    {
                        "reason": forced_reason,
                        "entropy": entropy_value,
                        "peak_entropy": peak_entropy,
                        "coherence": coherence_value,
                        "cross_module_openings": self._cross_module_openings,
                    },
                )
            else:
                self._phase = self._next_phase(self._phase)
                if self._phase == ExplorationPhase.DESEGREGATION:
                    self._cross_module_openings = min(
                        self._config.max_cross_module_openings,
                        self._cross_module_openings + 1,
                    )
                elif self._phase == ExplorationPhase.DIVERSITY:
                    self._diversity_gain = self._config.diversity_multiplier
                elif self._phase == ExplorationPhase.REINTEGRATION:
                    self._diversity_gain = 1.0

            if self._phase != prev_phase:
                self._append_event(
                    "phase_transition",
                    {
                        "from_phase": prev_phase.value,
                        "to_phase": self._phase.value,
                        "entropy": entropy_value,
                        "peak_entropy": peak_entropy,
                        "coherence": coherence_value,
                        "cross_module_openings": self._cross_module_openings,
                    },
                )
            return self._phase

    def reintegrate(self, coherence: float) -> tuple[bool, dict[str, float]]:
        with self._lock:
            if self._phase != ExplorationPhase.REINTEGRATION:
                raise ExplorationContractError("reintegrate denied: phase must be reintegration")
            if self._prior_weights_backup is None:
                raise ExplorationContractError("reintegrate denied: no prior backup")
            coherence_value = self._require_finite_real(
                name="coherence",
                value=coherence,
                message="reintegrate denied: coherence must be a finite real number",
            )

            restored = dict(self._prior_weights_backup)
            self._reintegration_coherence = coherence_value
            success = coherence_value >= self._config.reintegration_coherence_threshold
            terminal_event = "reintegration_success" if success else "reintegration_failed"
            terminal_reason = "threshold_met" if success else "coherence_below_threshold"

            self._apply_restore_or_raise(restored, attempted_terminal_event=terminal_event)

            self._reintegration_outcome = (
                ReintegrationOutcome.SUCCESS if success else ReintegrationOutcome.FAILED
            )
            self._append_event(
                terminal_event,
                {
                    "coherence": coherence_value,
                    "restored_key_count": len(restored),
                    "reason": terminal_reason,
                },
            )
            self._reset_state()
            return success, restored

    def emergency_exit(self, reason: str) -> dict[str, float]:
        with self._lock:
            if self._phase == ExplorationPhase.INACTIVE or self._prior_weights_backup is None:
                raise ExplorationContractError("emergency_exit denied: gate is inactive")

            restored = dict(self._prior_weights_backup)
            self._phase = ExplorationPhase.REINTEGRATION
            self._forced_halt_reason = reason

            self._apply_restore_or_raise(restored, attempted_terminal_event="emergency_exit")

            self._reintegration_outcome = ReintegrationOutcome.EMERGENCY_EXIT
            self._append_event(
                "emergency_exit",
                {
                    "reason": reason,
                    "restored_key_count": len(restored),
                    "entropy": self._entropy_budget.current_entropy,
                    "peak_entropy": self._entropy_budget.peak_entropy,
                    "coherence": self._reintegration_coherence,
                },
            )
            self._reset_state()
            return restored

    def apply_external_safety_signal(
        self, *, kill_switch_active: bool, stressed_state: bool
    ) -> dict[str, float] | None:
        with self._lock:
            if not self.is_active():
                return None
            if kill_switch_active:
                return self.emergency_exit("kill_switch_active")
            if stressed_state:
                return self.emergency_exit("stressed_escalation")
            return None

    def audit_log(self) -> list[RebusAuditEvent]:
        with self._lock:
            return [
                RebusAuditEvent(
                    ts=event.ts,
                    event=event.event,
                    cycle_id=event.cycle_id,
                    phase=event.phase,
                    bars_elapsed=event.bars_elapsed,
                    details=MappingProxyType(dict(event.details)),
                )
                for event in self._audit_log
            ]

    def is_active(self) -> bool:
        return self._phase != ExplorationPhase.INACTIVE

    def _next_phase(self, phase: ExplorationPhase) -> ExplorationPhase:
        if phase == ExplorationPhase.ATTENUATION:
            return ExplorationPhase.DESEGREGATION
        if phase == ExplorationPhase.DESEGREGATION:
            return ExplorationPhase.DIVERSITY
        if phase == ExplorationPhase.DIVERSITY:
            return ExplorationPhase.REINTEGRATION
        return phase

    def _append_event(self, event: str, details: Mapping[str, object]) -> None:
        frozen_details = MappingProxyType(deepcopy(dict(details)))
        self._audit_log.append(
            RebusAuditEvent(
                ts=utc_now(),
                event=event,
                cycle_id=self._cycle_id,
                phase=self._phase,
                bars_elapsed=self._bars_elapsed,
                details=frozen_details,
            )
        )

    def _apply_restore_or_raise(
        self,
        restored: Mapping[str, float],
        *,
        attempted_terminal_event: str,
    ) -> None:
        if self._restore_callback is None:
            self._append_event(
                "restore_apply_failed",
                {
                    "attempted_terminal_event": attempted_terminal_event,
                    "reason": "restore_callback_missing",
                },
            )
            raise ExplorationContractError("restore callback missing during terminal restore")
        self._apply_callback_or_raise(
            self._restore_callback,
            restored,
            failure_event="restore_apply_failed",
            failure_reason="restore_callback_not_confirmed",
            attempted_terminal_event=attempted_terminal_event,
        )

    def _apply_callback_or_raise(
        self,
        callback: Callable[[Mapping[str, float]], bool],
        payload: Mapping[str, float],
        *,
        failure_event: str,
        failure_reason: str,
        attempted_terminal_event: str | None = None,
    ) -> None:
        try:
            applied = callback(payload)
        except Exception as exc:
            details: dict[str, object] = {"reason": f"{failure_reason}_exception"}
            if attempted_terminal_event is not None:
                details["attempted_terminal_event"] = attempted_terminal_event
            self._append_event(failure_event, details)
            raise ExplorationContractError("callback apply raised exception") from exc
        if applied is not True:
            details = {"reason": failure_reason}
            if attempted_terminal_event is not None:
                details["attempted_terminal_event"] = attempted_terminal_event
            self._append_event(failure_event, details)
            raise ExplorationContractError("callback apply did not confirm")

    def _require_finite_real(
        self,
        *,
        name: str,
        value: object,
        message: str,
    ) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ExplorationContractError(message)
        try:
            if not isfinite(value):
                raise ExplorationContractError(message)
        except (TypeError, ValueError) as exc:
            raise ExplorationContractError(message) from exc
        return float(value)

    def _validate_config(self, config: RebusConfig) -> None:
        if not (0.0 < config.attenuation_factor <= 1.0):
            raise ValueError("attenuation_factor must be in (0, 1]")
        if config.max_duration_bars < 1:
            raise ValueError("max_duration_bars must be >= 1")
        if config.max_cross_module_openings < 0:
            raise ValueError("max_cross_module_openings must be >= 0")
        if config.max_audit_events < 1:
            raise ValueError("max_audit_events must be >= 1")
        if not (0.0 <= config.reintegration_coherence_threshold <= 1.0):
            raise ValueError("reintegration_coherence_threshold must be in [0,1]")
        if not (0.0 <= config.activation_coherence_threshold <= 1.0):
            raise ValueError("activation_coherence_threshold must be in [0,1]")

    def _reset_state(self) -> None:
        self._phase = ExplorationPhase.INACTIVE
        self._activated_at = None
        self._bars_elapsed = 0
        self._entropy_budget = EntropyBudget(max_entropy=self._entropy_budget.max_entropy)
        self._forced_halt_reason = None
        self._reintegration_coherence = 0.0
        self._reintegration_outcome = ReintegrationOutcome.NOT_RUN
        self._cycle_id = None
        self._prior_weights_backup = None
        self._restore_callback = None
        self._cross_module_openings = 0
        self._diversity_gain = 1.0
