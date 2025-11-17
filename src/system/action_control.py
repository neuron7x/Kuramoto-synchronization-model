"""Action safety controls enforcing TACL stability and mandate policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol

from src.audit.audit_logger import AuditLogger


class ActionClass(str, Enum):
    """Classification for system actions."""

    A0 = "A0"
    A1 = "A1"
    A2 = "A2"


class SystemState(str, Enum):
    """High-level operating states recognised by the control policy."""

    NORMAL = "normal"
    DEGRADED = "degraded"
    CRISIS = "crisis"


@dataclass(frozen=True, slots=True)
class FreeEnergyForecast:
    """Projection of the system free energy before executing an action."""

    current: float
    projected: float
    recovery_path: str | None = None
    recovery_window: float | None = None
    guarantees_descent: bool = False


@dataclass(frozen=True, slots=True)
class TaclDecision:
    """Decision rendered by the TACL gate."""

    allowed: bool
    reason: str | None = None
    requires_recovery: bool = False


class TaclGate:
    """Apply the Monotonic Free Energy Descent rule before an action executes."""

    def __init__(self, *, max_free_energy: float | None = None) -> None:
        self._max_free_energy = max_free_energy

    def evaluate(self, forecast: FreeEnergyForecast) -> TaclDecision:
        """Return whether the action satisfies the TACL energy constraints."""

        if forecast.projected < 0 or forecast.current < 0:
            raise ValueError("Free energy values must be non-negative")

        if (
            self._max_free_energy is not None
            and forecast.projected > self._max_free_energy
        ):
            return TaclDecision(
                allowed=False,
                reason=(
                    f"projected free energy {forecast.projected:.3f} exceeds "
                    f"limit {self._max_free_energy:.3f}"
                ),
            )

        if forecast.projected <= forecast.current:
            return TaclDecision(allowed=True)

        if forecast.guarantees_descent and forecast.recovery_path:
            if forecast.recovery_window is not None and forecast.recovery_window <= 0:
                return TaclDecision(
                    allowed=False,
                    reason="recovery window must be positive when guarantees_descent is true",
                )
            return TaclDecision(
                allowed=True,
                requires_recovery=True,
                reason=(
                    "monotonicity temporarily violated but recovery path "
                    f"'{forecast.recovery_path}' guarantees descent"
                ),
            )

        return TaclDecision(
            allowed=False,
            reason=(
                "projected free energy increases without a guaranteed recovery path"
            ),
        )


@dataclass(frozen=True, slots=True)
class StatePermission:
    """Mandate controls applicable to a module for a given system state."""

    allowed_classes: frozenset[ActionClass]
    allowed_targets: frozenset[str] = frozenset()
    manual_corridor: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_classes", frozenset(self.allowed_classes))
        object.__setattr__(self, "allowed_targets", frozenset(self.allowed_targets))
        object.__setattr__(self, "manual_corridor", frozenset(self.manual_corridor))


@dataclass(frozen=True, slots=True)
class MandateDecision:
    """Outcome of evaluating a mandate for a specific action."""

    allowed: bool
    reason: str | None
    engaged_corridor: bool


@dataclass(frozen=True, slots=True)
class Mandate:
    """Declarative scope describing what a module is authorised to perform."""

    module: str
    allowed_classes: frozenset[ActionClass]
    object_scope: frozenset[str] = frozenset()
    state_permissions: Mapping[SystemState, StatePermission] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.module or not self.module.strip():
            raise ValueError("Mandate module must be a non-empty string")
        object.__setattr__(self, "module", self.module.strip())
        object.__setattr__(self, "allowed_classes", frozenset(self.allowed_classes))
        object.__setattr__(self, "object_scope", frozenset(self.object_scope))

    def allows(self, intent: "ActionIntent", state: SystemState) -> MandateDecision:
        """Return whether ``intent`` is authorised for ``state`` under this mandate."""

        if intent.action_class not in self.allowed_classes:
            return MandateDecision(
                allowed=False,
                reason=f"action class {intent.action_class.value} not in module mandate",
                engaged_corridor=False,
            )

        if self.object_scope and (
            intent.target is None or intent.target not in self.object_scope
        ):
            return MandateDecision(
                allowed=False,
                reason="target outside module object scope",
                engaged_corridor=False,
            )

        permission = self.state_permissions.get(state)
        if permission is None:
            return MandateDecision(
                allowed=False,
                reason=f"state {state.value} not covered by module mandate",
                engaged_corridor=False,
            )

        if intent.action_class not in permission.allowed_classes:
            return MandateDecision(
                allowed=False,
                reason=(
                    f"action class {intent.action_class.value} not permitted in state"
                ),
                engaged_corridor=False,
            )

        allowed_targets = permission.allowed_targets or self.object_scope
        if allowed_targets and (
            intent.target is None or intent.target not in allowed_targets
        ):
            return MandateDecision(
                allowed=False,
                reason="target not permitted for state",
                engaged_corridor=False,
            )

        engaged_corridor = False
        if state is SystemState.CRISIS and intent.action_class is ActionClass.A2:
            if intent.operation in permission.manual_corridor:
                engaged_corridor = True
            else:
                return MandateDecision(
                    allowed=False,
                    reason="action not part of crisis manual corridor",
                    engaged_corridor=False,
                )

        return MandateDecision(
            allowed=True, reason=None, engaged_corridor=engaged_corridor
        )


@dataclass(frozen=True, slots=True)
class ActionIntent:
    """Description of the action a module wishes to execute."""

    module: str
    action_class: ActionClass
    operation: str
    description: str
    target: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.module or not self.module.strip():
            raise ValueError("module must be a non-empty string")
        if not self.operation or not self.operation.strip():
            raise ValueError("operation must be a non-empty string")
        if not self.description or not self.description.strip():
            raise ValueError("description must be a non-empty string")
        object.__setattr__(self, "module", self.module.strip())
        object.__setattr__(self, "operation", self.operation.strip())
        object.__setattr__(self, "description", self.description.strip())
        if self.target is not None:
            object.__setattr__(self, "target", self.target.strip())


@dataclass(frozen=True, slots=True)
class ActionDecision:
    """Aggregate decision for a proposed action."""

    intent: ActionIntent
    state: SystemState
    forecast: FreeEnergyForecast | None
    mandate: MandateDecision
    tacl: TaclDecision | None
    allowed: bool
    reason: str | None


class ActionAuditSink(Protocol):
    """Protocol describing how action decisions are recorded."""

    def record(self, decision: ActionDecision) -> None:
        """Persist or forward the decision for auditing."""


class AuditLoggerActionSink:
    """Adapter that persists action attempts using :class:`AuditLogger`."""

    def __init__(self, audit_logger: AuditLogger, *, ip_address: str = "::1") -> None:
        self._audit_logger = audit_logger
        self._ip_address = ip_address

    def record(
        self, decision: ActionDecision
    ) -> None:  # pragma: no cover - thin wrapper
        forecast = decision.forecast
        tacl = decision.tacl
        intent = decision.intent
        details = {
            "module": intent.module,
            "action_class": intent.action_class.value,
            "operation": intent.operation,
            "description": intent.description,
            "target": intent.target,
            "metadata": dict(intent.metadata),
            "system_state": decision.state.value,
            "mandate_allowed": decision.mandate.allowed,
            "mandate_reason": decision.mandate.reason,
            "manual_corridor": decision.mandate.engaged_corridor,
            "tacl_allowed": None if tacl is None else tacl.allowed,
            "tacl_reason": None if tacl is None else tacl.reason,
            "tacl_requires_recovery": None if tacl is None else tacl.requires_recovery,
            "forecast": (
                None
                if forecast is None
                else {
                    "current": forecast.current,
                    "projected": forecast.projected,
                    "recovery_path": forecast.recovery_path,
                    "recovery_window": forecast.recovery_window,
                    "guarantees_descent": forecast.guarantees_descent,
                }
            ),
            "allowed": decision.allowed,
            "decision_reason": decision.reason,
        }
        self._audit_logger.log_event(
            event_type="system.action.attempt",
            actor=intent.module,
            ip_address=self._ip_address,
            details=details,
        )


class ActionGovernor:
    """Evaluate proposed actions against stability and mandate constraints."""

    def __init__(
        self,
        mandates: Mapping[str, Mandate],
        *,
        tacl_gate: TaclGate,
        audit_sink: ActionAuditSink | None = None,
    ) -> None:
        if not mandates:
            raise ValueError("At least one module mandate must be configured")
        mandate_map: dict[str, Mandate] = {}
        for mandate in mandates.values():
            module_name = mandate.module.strip().lower()
            if not module_name:
                raise ValueError("Mandate module names must be non-empty")
            mandate_map[module_name] = mandate
        self._mandates = mandate_map
        self._tacl_gate = tacl_gate
        self._audit_sink = audit_sink

    def evaluate(
        self,
        intent: ActionIntent,
        *,
        state: SystemState,
        forecast: FreeEnergyForecast | None = None,
    ) -> ActionDecision:
        """Return the combined decision for ``intent`` given ``state``."""

        if not isinstance(intent.action_class, ActionClass):
            raise ValueError("intent.action_class must be a valid ActionClass")

        module_key = intent.module.strip().lower()
        mandate = self._mandates.get(module_key)
        if mandate is None:
            raise ValueError(f"No mandate defined for module '{intent.module}'")

        mandate_decision = mandate.allows(intent, state)

        tacl_decision: TaclDecision | None = None
        if intent.action_class is ActionClass.A0:
            allowed = mandate_decision.allowed
            reason = mandate_decision.reason
        else:
            if not mandate_decision.allowed:
                allowed = False
                reason = mandate_decision.reason
            else:
                if forecast is None:
                    raise ValueError(
                        "Free energy forecast required for non-passive actions"
                    )
                tacl_decision = self._tacl_gate.evaluate(forecast)
                if tacl_decision.allowed:
                    allowed = True
                    reason = tacl_decision.reason
                else:
                    allowed = False
                    reason = tacl_decision.reason

        decision = ActionDecision(
            intent=intent,
            state=state,
            forecast=forecast,
            mandate=mandate_decision,
            tacl=tacl_decision,
            allowed=allowed,
            reason=reason,
        )

        if self._audit_sink is not None:
            self._audit_sink.record(decision)

        return decision


__all__ = [
    "ActionClass",
    "ActionDecision",
    "ActionGovernor",
    "ActionIntent",
    "ActionAuditSink",
    "AuditLoggerActionSink",
    "FreeEnergyForecast",
    "Mandate",
    "MandateDecision",
    "StatePermission",
    "SystemState",
    "TaclDecision",
    "TaclGate",
]
