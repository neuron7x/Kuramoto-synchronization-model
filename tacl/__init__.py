# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Thermodynamic Autonomic Control Layer (TACL) utilities."""

from .behavioral_contract import (
    BehavioralContract,
    BehavioralContractReport,
    BehavioralContractViolation,
    ContractBreach,
)
from .degradation import DegradationPolicy, DegradationReport, apply_degradation
from .dr_free import (
    AmbiguitySet,
    DRFreeEnergyModel,
    DRFreeResult,
    robust_energy_state,
)
from .energy_model import (
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
    EnergyMetrics,
    EnergyModel,
    EnergyValidationError,
    EnergyValidationResult,
    EnergyValidator,
)
from .rebus_protocol import (
    REBUS_PROTOCOL_NAME,
    apply_external_controller,
    build_protocol,
    clear_registered_protocols,
    get_registered_protocol,
    protocol_schema_keys,
    register_protocol,
)
from .risk_gating import (
    PreActionContext,
    PreActionDecision,
    PreActionFilter,
    RiskGatingConfig,
    RiskGatingEngine,
)
from .validate import load_scenarios

__all__ = [
    "DEFAULT_THRESHOLDS",
    "DEFAULT_WEIGHTS",
    "EnergyMetrics",
    "EnergyModel",
    "EnergyValidationError",
    "EnergyValidationResult",
    "EnergyValidator",
    "DegradationPolicy",
    "DegradationReport",
    "apply_degradation",
    "BehavioralContract",
    "BehavioralContractReport",
    "BehavioralContractViolation",
    "ContractBreach",
    "PreActionContext",
    "PreActionDecision",
    "PreActionFilter",
    "RiskGatingConfig",
    "RiskGatingEngine",
    "load_scenarios",
    "REBUS_PROTOCOL_NAME",
    "build_protocol",
    "register_protocol",
    "get_registered_protocol",
    "clear_registered_protocols",
    "apply_external_controller",
    "protocol_schema_keys",
    "AmbiguitySet",
    "DRFreeEnergyModel",
    "DRFreeResult",
    "robust_energy_state",
]
