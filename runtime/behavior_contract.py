# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Thermodynamic Autonomic Control Layer (TACL) behaviour contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple

from runtime.dual_approval import requires_dual_approval
from runtime.kill_switch import is_kill_switch_active


class ActionClass(Enum):
    A0_OBSERVATION = "A0"
    A1_LOCAL_CORRECTION = "A1"
    A2_SYSTEMIC = "A2"


class SystemState(Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    CRISIS = "CRISIS"


@dataclass(slots=True)
class ModuleMandate:
    allowed_actions: Tuple[ActionClass, ...]
    allowed_states: Tuple[SystemState, ...]
    allowed_scope: Tuple[str, ...]
    escalation_policy: Dict[str, str]


@dataclass(slots=True)
class TACLDecision:
    allowed: bool
    reason: str


MANDATES: Dict[str, ModuleMandate] = {
    "VLPO_Core_Filter": ModuleMandate(
        allowed_actions=(ActionClass.A0_OBSERVATION, ActionClass.A1_LOCAL_CORRECTION),
        allowed_states=(SystemState.NORMAL, SystemState.DEGRADED, SystemState.CRISIS),
        allowed_scope=("input_signals", "internal_thresholds"),
        escalation_policy={"A1": "log_only", "CRISIS": "no_A2"},
    ),
    "thermo_controller": ModuleMandate(
        allowed_actions=(
            ActionClass.A0_OBSERVATION,
            ActionClass.A1_LOCAL_CORRECTION,
            ActionClass.A2_SYSTEMIC,
        ),
        allowed_states=(SystemState.NORMAL, SystemState.DEGRADED, SystemState.CRISIS),
        allowed_scope=("topology", "metrics", "system_state"),
        escalation_policy={"A2": "dual_approval", "CRISIS": "downgrade_to_A1"},
    ),
    "crisis_ga": ModuleMandate(
        allowed_actions=(ActionClass.A0_OBSERVATION, ActionClass.A1_LOCAL_CORRECTION),
        allowed_states=(SystemState.NORMAL, SystemState.DEGRADED),
        allowed_scope=("population_params", "mutation_rates"),
        escalation_policy={"A1": "tacl_gate", "CRISIS": "no_mutations"},
    ),
}


def register_mandate(module_name: str, mandate: ModuleMandate) -> None:
    MANDATES[module_name] = mandate


def classify_action(description: str) -> ActionClass:
    lowered = description.lower()
    if any(keyword in lowered for keyword in ("read", "inspect", "observe", "simulate")):
        return ActionClass.A0_OBSERVATION
    if any(keyword in lowered for keyword in ("update", "adjust", "tune", "local")):
        return ActionClass.A1_LOCAL_CORRECTION
    if any(keyword in lowered for keyword in ("change", "deploy", "topology", "order", "system")):
        return ActionClass.A2_SYSTEMIC
    raise ValueError(f"Unable to classify action '{description}' into A0/A1/A2")


def get_current_state(F_current: float, F_baseline: float) -> SystemState:
    if F_baseline <= 0:
        return SystemState.NORMAL
    deviation = (F_current - F_baseline) / F_baseline
    if deviation >= 0.2:
        return SystemState.CRISIS
    if deviation >= 0.1:
        return SystemState.DEGRADED
    return SystemState.NORMAL


def tacl_gate(
    *,
    module_name: str,
    action_class: ActionClass,
    system_state: SystemState,
    F_now: float,
    F_next: float,
    epsilon: float,
    recovery_path: bool,
    dual_approved: bool,
) -> TACLDecision:
    if is_kill_switch_active():
        return TACLDecision(False, "kill_switch_active")

    mandate = MANDATES.get(module_name)
    if mandate is None:
        return TACLDecision(False, f"unknown_module:{module_name}")

    if action_class not in mandate.allowed_actions:
        return TACLDecision(False, f"action_not_allowed:{action_class.value}")

    if system_state not in mandate.allowed_states:
        return TACLDecision(False, f"state_not_allowed:{system_state.value}")

    if system_state is SystemState.CRISIS and action_class is ActionClass.A2_SYSTEMIC:
        return TACLDecision(False, "crisis_downgrade")

    if action_class is ActionClass.A2_SYSTEMIC and requires_dual_approval(module_name):
        if not dual_approved:
            return TACLDecision(False, "dual_approval_missing")

    if F_next > F_now + epsilon:
        return TACLDecision(False, "free_energy_spike")
    if F_next > F_now and not recovery_path:
        return TACLDecision(False, "no_recovery_path")

    return TACLDecision(True, "allowed")


__all__ = [
    "ActionClass",
    "ModuleMandate",
    "SystemState",
    "TACLDecision",
    "MANDATES",
    "register_mandate",
    "classify_action",
    "get_current_state",
    "tacl_gate",
]
