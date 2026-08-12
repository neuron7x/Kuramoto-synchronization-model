# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Advanced neurobiological trading components."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "AgencyControlNetwork",
    "GrangerResult",
    "AICConfig",
    "AlertThresholds",
    "CandidateGenerator",
    "DecisionIntegratorWeights",
    "DopaminePredictionNetwork",
    "ECANeuroTradingAdapter",
    "EnhancedFractalNeuroeconomicCore",
    "IntegratedNeuroTradingSystem",
    "MarketContext",
    "MultiscaleFractalAnalyzer",
    "DivergenceConfig",
    "DivergenceOutput",
    "compute_divergence_convergence_phi",
    "AdvancedNeuroEconCore",
    "DecisionOption",
    "NeuroAdvancedConfig",
    "NeuroDecisionIntegrator",
    "NeuroRiskManager",
    "NeuroStateMonitor",
    "NeuroplasticReinforcementEngine",
    "NREConfig",
    "PolicyBounds",
    "TradeOutcome",
    "TradeResult",
    "DPAConfig",
    "QuantumBeliefUpdate",
    "quantum_active_update",
    "quantum_relative_entropy",
    "to_density_matrix",
    "von_neumann_entropy",
    "granger_causality",
    "FractalMotivationController",
    "FractalSignalTracker",
]

_MODULE_EXPORTS: dict[str, tuple[str, ...]] = {
    "core.neuro.advanced.aic": ("AgencyControlNetwork",),
    "core.neuro.advanced.causal": ("GrangerResult", "granger_causality"),
    "core.neuro.advanced.config": (
        "AICConfig",
        "AlertThresholds",
        "DecisionIntegratorWeights",
        "DPAConfig",
        "NeuroAdvancedConfig",
        "NREConfig",
        "PolicyBounds",
    ),
    "core.neuro.advanced.divergence": (
        "DivergenceConfig",
        "DivergenceOutput",
        "compute_divergence_convergence_phi",
    ),
    "core.neuro.advanced.dpa": ("DopaminePredictionNetwork",),
    "core.neuro.advanced.integrated": (
        "CandidateGenerator",
        "ECANeuroTradingAdapter",
        "EnhancedFractalNeuroeconomicCore",
        "IntegratedNeuroTradingSystem",
        "MarketContext",
        "MultiscaleFractalAnalyzer",
        "NeuroDecisionIntegrator",
        "NeuroRiskManager",
        "TradeOutcome",
        "TradeResult",
    ),
    "core.neuro.advanced.monitor": ("NeuroStateMonitor",),
    "core.neuro.advanced.motivation": (
        "FractalMotivationController",
        "FractalSignalTracker",
    ),
    "core.neuro.advanced.neuroecon": (
        "AdvancedNeuroEconCore",
        "DecisionOption",
    ),
    "core.neuro.advanced.nre": ("NeuroplasticReinforcementEngine",),
    "core.neuro.advanced.quantum": (
        "QuantumBeliefUpdate",
        "quantum_active_update",
        "quantum_relative_entropy",
        "to_density_matrix",
        "von_neumann_entropy",
    ),
}


def __getattr__(name: str) -> Any:
    """Lazily import advanced neuro modules to avoid hard torch dependency."""

    for module_name, exports in _MODULE_EXPORTS.items():
        if name in exports:
            module = importlib.import_module(module_name)
            value = getattr(module, name)
            globals()[name] = value
            return value
    raise AttributeError(f"module 'core.neuro.advanced' has no attribute '{name}'")
