"""Behavioral contract enforcement for the TradePulse TACL layer.

This module implements the behavioral contract that governs how agents are
allowed to act inside the TradePulse environment.  The implementation mirrors
the specification outlined in the "Поведінковий контракт" document and focuses
on a deterministic, auditable decision pipeline.  The core responsibilities
include:

* Computing the composite Free Energy (FE) score used to quantify system stress.
* Maintaining the agent state-machine that switches between action potential
  and calm potential based on FE thresholds and kill-switch signals.
* Validating whether a proposed action is admissible while observing mandates,
  dual approval constraints, and monotonic FE descent guarantees.
* Producing immutable audit records that capture the full rationale for every
  decision so that actions remain explainable and reproducible.

The module is intentionally self-contained and side-effect free which makes it
straightforward to exercise in tests and during incident response replays.  It
does not persist audit events itself; instead it emits structured dataclasses
that callers can hand to the immutable storage of their choice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Iterable, Mapping, MutableMapping, Sequence


class SystemBand(Enum):
    """Qualitative band for the computed Free Energy (FE)."""

    GREEN = auto()
    YELLOW = auto()
    RED = auto()


class AgentState(Enum):
    """Lifecycle phases that control whether an agent may initiate actions."""

    IDLE = auto()
    ACTION_POTENTIAL = auto()
    ELEVATED = auto()
    QUIESCED = auto()
    KILL = auto()


class ActionClass(Enum):
    """Classification of actions recognised by the behavioral contract."""

    OBSERVATION = auto()
    REMEDIATION = auto()
    INTER_MODULAR = auto()
    OUTBOUND = auto()
    ADMINISTRATIVE = auto()


class MandateRole(Enum):
    """Supported mandate roles."""

    OBSERVER = "observer"
    REMEDIATOR = "remediator"
    CONFIG_MANAGER = "config-manager"
    OUTBOUND_AGENT = "outbound-agent"
    ADMIN = "admin"
    SECURITY_OFFICER = "security-officer"
    APPROVER = "approver"


@dataclass(frozen=True, slots=True)
class Mandate:
    """Formal authorisation for an agent."""

    agent_id: str
    role: MandateRole
    scope: str
    expiry: datetime
    constraints: Mapping[str, str] | None
    issued_by: str
    signature: str

    def is_valid(self, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(tz=timezone.utc)
        return current <= self.expiry


@dataclass(frozen=True, slots=True)
class Approval:
    approver_id: str
    signature: str
    timestamp: datetime
    rationale: str


@dataclass(frozen=True, slots=True)
class StabilizationPlan:
    description: str
    fe_ceiling: float
    verification_steps: Sequence[str]

    def guarantees_monotonic_descent(self, *, target_fe: float) -> bool:
        """Return True when the plan asserts FE will not exceed ``target_fe``."""

        return self.fe_ceiling <= target_fe


@dataclass(frozen=True, slots=True)
class Forecast:
    fe_after: float
    stabilization_plan: StabilizationPlan | None = None

    @property
    def has_immediate_stabilization_plan(self) -> bool:
        return self.stabilization_plan is not None


@dataclass(frozen=True, slots=True)
class ActionRequest:
    agent_id: str
    action_class: ActionClass
    description: str
    critical: bool
    mandate: Mandate
    forecast: Forecast
    approvals: Sequence[Approval] = ()
    correlation_id: str = ""


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    timestamp: datetime
    correlation_id: str
    agent_id: str
    role: MandateRole
    mandate_signature: str
    action_class: ActionClass
    action_description: str
    system_state_before: AgentState
    fe_before: float
    forecast_fe_after: float
    stabilization_plan: StabilizationPlan | None
    approvals: Sequence[Approval]
    decision: str
    system_state_after: AgentState
    fe_after: float | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    reason: str | None
    audit_event: AuditEvent


@dataclass(frozen=True, slots=True)
class FreeEnergyInputs:
    resource_pressure: float
    latency_risk: float
    safety_violations: float
    external_impact_risk: float

    def as_dict(self) -> Mapping[str, float]:
        return {
            "resource_pressure": self.resource_pressure,
            "latency_risk": self.latency_risk,
            "safety_violations": self.safety_violations,
            "external_impact_risk": self.external_impact_risk,
        }


class FreeEnergyModel:
    """Compute the composite Free Energy (FE) scalar."""

    def __init__(
        self,
        *,
        weights: Mapping[str, float] | None = None,
        minimums: Mapping[str, float] | None = None,
    ) -> None:
        default_weights: Mapping[str, float] = {
            "resource_pressure": 0.35,
            "latency_risk": 0.3,
            "safety_violations": 0.2,
            "external_impact_risk": 0.15,
        }
        default_minimums: Mapping[str, float] = {
            "resource_pressure": 0.0,
            "latency_risk": 0.0,
            "safety_violations": 0.0,
            "external_impact_risk": 0.0,
        }
        self._weights = dict(weights or default_weights)
        self._minimums = dict(minimums or default_minimums)
        unknown = set(self._weights) ^ set(self._minimums)
        if unknown:
            raise ValueError(
                "weights and minimums must reference the same inputs"
                f" (mismatch: {sorted(unknown)})"
            )
        if any(weight < 0 for weight in self._weights.values()):
            raise ValueError("weights must be non-negative")
        if sum(self._weights.values()) <= 0:
            raise ValueError("weights must sum to a positive value")

    def compute(self, inputs: FreeEnergyInputs) -> float:
        values = inputs.as_dict()
        total = 0.0
        for name, weight in self._weights.items():
            value = max(values[name], self._minimums[name])
            total += weight * value
        return total

    def classify(self, inputs: FreeEnergyInputs, *, thresholds: Mapping[SystemBand, float]) -> tuple[float, SystemBand]:
        fe = self.compute(inputs)
        if fe <= thresholds[SystemBand.GREEN]:
            band = SystemBand.GREEN
        elif fe <= thresholds[SystemBand.YELLOW]:
            band = SystemBand.YELLOW
        else:
            band = SystemBand.RED
        return fe, band


class KillSwitch:
    """Observable kill-switch state."""

    def __init__(self) -> None:
        self._activated = False

    def activate(self) -> None:
        self._activated = True

    def reset(self) -> None:
        self._activated = False

    @property
    def activated(self) -> bool:
        return self._activated


class PolicyMatrix:
    """Matrix capturing which action classes are permitted in each state."""

    def __init__(self) -> None:
        self._matrix: MutableMapping[tuple[ActionClass, AgentState], bool] = {}
        allowed_pairs = {
            (ActionClass.OBSERVATION, AgentState.ACTION_POTENTIAL),
            (ActionClass.OBSERVATION, AgentState.ELEVATED),
            (ActionClass.OBSERVATION, AgentState.QUIESCED),
            (ActionClass.REMEDIATION, AgentState.ACTION_POTENTIAL),
            (ActionClass.REMEDIATION, AgentState.ELEVATED),
            (ActionClass.REMEDIATION, AgentState.QUIESCED),
            (ActionClass.INTER_MODULAR, AgentState.ACTION_POTENTIAL),
            (ActionClass.OUTBOUND, AgentState.ACTION_POTENTIAL),
            (ActionClass.ADMINISTRATIVE, AgentState.ACTION_POTENTIAL),
        }
        for action_state in allowed_pairs:
            self._matrix[action_state] = True

    def allows(self, action_class: ActionClass, state: AgentState) -> bool:
        return self._matrix.get((action_class, state), False)


class TACLController:
    """Behavioral contract arbiter."""

    def __init__(
        self,
        *,
        fe_thresholds: Mapping[SystemBand, float] | None = None,
        energy_model: FreeEnergyModel | None = None,
        policy_matrix: PolicyMatrix | None = None,
        kill_switch: KillSwitch | None = None,
    ) -> None:
        self._fe_thresholds = dict(
            fe_thresholds
            or {
                SystemBand.GREEN: 0.6,
                SystemBand.YELLOW: 1.1,
                SystemBand.RED: float("inf"),
            }
        )
        self._energy_model = energy_model or FreeEnergyModel()
        self._policy_matrix = policy_matrix or PolicyMatrix()
        self._kill_switch = kill_switch or KillSwitch()
        self._state = AgentState.IDLE
        self._current_fe = 0.0

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def current_fe(self) -> float:
        return self._current_fe

    @property
    def kill_switch(self) -> KillSwitch:
        return self._kill_switch

    def observe_system(self, inputs: FreeEnergyInputs) -> tuple[float, SystemBand]:
        fe, band = self._energy_model.classify(inputs, thresholds=self._fe_thresholds)
        self._current_fe = fe
        self._transition_state(band)
        return fe, band

    def _transition_state(self, band: SystemBand) -> None:
        if self._kill_switch.activated:
            self._state = AgentState.KILL
            return
        if band == SystemBand.GREEN:
            self._state = AgentState.ACTION_POTENTIAL
        elif band == SystemBand.YELLOW:
            self._state = AgentState.ELEVATED
        else:
            self._state = AgentState.QUIESCED

    def _has_dual_approval(self, approvals: Sequence[Approval]) -> bool:
        unique = {approval.approver_id for approval in approvals}
        return len(unique) >= 2

    def _validate_stabilization_plan(self, plan: StabilizationPlan | None) -> bool:
        if plan is None:
            return False
        return plan.guarantees_monotonic_descent(target_fe=self._current_fe)

    def _validate_mandate(self, request: ActionRequest, *, now: datetime | None = None) -> bool:
        if request.agent_id != request.mandate.agent_id:
            return False
        return request.mandate.is_valid(now=now)

    def _class_allowed(self, request: ActionRequest) -> bool:
        return self._policy_matrix.allows(request.action_class, self._state)

    def allow_action(
        self,
        request: ActionRequest,
        *,
        now: datetime | None = None,
    ) -> Decision:
        """Evaluate whether the requested action complies with the contract."""

        timestamp = now or datetime.now(tz=timezone.utc)
        state_before = self._state
        fe_before = self._current_fe
        reason: str | None = None
        allowed = False
        if self._kill_switch.activated:
            reason = "kill-switch"
        elif not self._validate_mandate(request, now=timestamp):
            reason = "invalid_mandate"
        elif not self._class_allowed(request):
            reason = "class_not_allowed"
        else:
            forecast = request.forecast
            if forecast.fe_after > self._current_fe:
                plan = forecast.stabilization_plan
                plan_valid = self._validate_stabilization_plan(plan)
                if not (forecast.has_immediate_stabilization_plan and plan_valid):
                    reason = "violates_monotonic_fe"
                elif plan is not None and forecast.fe_after > plan.fe_ceiling:
                    reason = "violates_monotonic_fe"
            if reason is None and request.critical and not self._has_dual_approval(request.approvals):
                reason = "missing_dual_approval"
        if reason is None:
            allowed = True

        next_state = state_before
        fe_after = None
        if allowed:
            fe_after = min(request.forecast.fe_after, self._current_fe)
            if self._kill_switch.activated:
                next_state = AgentState.KILL
            elif request.action_class == ActionClass.OBSERVATION and state_before == AgentState.QUIESCED:
                next_state = AgentState.QUIESCED
            else:
                # Re-evaluate the state based on the updated FE value.
                band = self._classify_fe_value(fe_after)
                if band == SystemBand.GREEN:
                    next_state = AgentState.ACTION_POTENTIAL
                elif band == SystemBand.YELLOW:
                    next_state = AgentState.ELEVATED
                else:
                    next_state = AgentState.QUIESCED
        if self._kill_switch.activated:
            next_state = AgentState.KILL

        audit = AuditEvent(
            event_id=f"audit-{request.correlation_id or request.agent_id}-{timestamp.timestamp():.0f}",
            timestamp=timestamp,
            correlation_id=request.correlation_id,
            agent_id=request.agent_id,
            role=request.mandate.role,
            mandate_signature=request.mandate.signature,
            action_class=request.action_class,
            action_description=request.description,
            system_state_before=state_before,
            fe_before=fe_before,
            forecast_fe_after=request.forecast.fe_after,
            stabilization_plan=request.forecast.stabilization_plan,
            approvals=request.approvals,
            decision="allow" if allowed else "deny",
            system_state_after=next_state,
            fe_after=fe_after,
            reason=reason,
        )
        if allowed:
            self._current_fe = fe_after if fe_after is not None else self._current_fe
        if self._kill_switch.activated:
            self._state = AgentState.KILL
        elif allowed:
            self._state = next_state
        return Decision(allowed=allowed, reason=reason, audit_event=audit)

    def _classify_fe_value(self, fe_value: float) -> SystemBand:
        if fe_value <= self._fe_thresholds[SystemBand.GREEN]:
            return SystemBand.GREEN
        if fe_value <= self._fe_thresholds[SystemBand.YELLOW]:
            return SystemBand.YELLOW
        return SystemBand.RED


def format_verification_steps(plan: StabilizationPlan | None) -> Iterable[str]:
    """Render verification steps for logging or UI surfaces."""

    if plan is None:
        return ()
    return tuple(plan.verification_steps)

