# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync policy module - decision making and governance."""

__CANONICAL__ = True

from .basal_ganglia import BasalGangliaPolicy
from .basal_ganglia import PolicyResult as LegacyPolicyResult
from .decision_trace import (
    DecisionTrace,
    Redaction,
    TraceScrubber,
    compute_input_hash,
    create_trace,
)
from .decision_types import (
    DECISION_PRIORITY,
    LEGACY_DECISION_MAP,
    DecisionType,
    resolve_decisions,
    to_legacy_decision,
)
from .policy_engine import (
    PolicyEngine,
    PolicyEngineConfig,
    PolicyModule,
    PolicyResult,
    SimplePolicyModule,
)

__all__ = [
    # Legacy (backward compatible)
    "BasalGangliaPolicy",
    "LegacyPolicyResult",
    # Decision types
    "DecisionType",
    "DECISION_PRIORITY",
    "LEGACY_DECISION_MAP",
    "resolve_decisions",
    "to_legacy_decision",
    # Decision trace
    "DecisionTrace",
    "Redaction",
    "TraceScrubber",
    "compute_input_hash",
    "create_trace",
    # Policy engine
    "PolicyEngine",
    "PolicyEngineConfig",
    "PolicyModule",
    "PolicyResult",
    "SimplePolicyModule",
]
