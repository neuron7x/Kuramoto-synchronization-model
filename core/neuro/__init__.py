"""Neuroscience-inspired modules for TradePulse."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "AMMConfig",
    "AdaptiveMarketMind",
    "AgencyControlNetwork",
    "AsyncDataLoader",
    "CheckpointManager",
    "CandidateGenerator",
    "DopaminePredictionNetwork",
    "ECANeuroTradingAdapter",
    "ECSInspiredRegulator",
    "ECSMetrics",
    "EEPFractalRegulator",
    "EnhancedFractalNeuroeconomicCore",
    "IntegratedNeuroTradingSystem",
    "MarketContext",
    "MixedPrecisionContext",
    "MarketPulse",
    "ProfileSnapshot",
    "RegulatorMetrics",
    "TrainingBatch",
    "TrainingComponent",
    "TrainingConfig",
    "TrainingEngine",
    "TrainingProfiler",
    "TrainingSample",
    "TrainingStepResult",
    "TrainingSummary",
    "TradeOutcome",
    "TradePulseNeuroAdapter",
    "TradeResult",
    "NeuroAdvancedConfig",
    "NeuroDecisionIntegrator",
    "NeuroRiskManager",
    "NeuroStateMonitor",
    "NeuroplasticReinforcementEngine",
    "ShockScenario",
    "ShockScenarioGenerator",
    "FractalMotivationController",
    "FractalMotivationEngine",
    "MotivationDecision",
    "RealTimeMotivationMonitor",
    # Quantile estimation
    "ExactQuantile",
    "P2Algorithm",
    "P2Quantile",
    # Position sizing
    "SizerConfig",
    "position_size",
    "kelly_size",
    "risk_parity_weight",
    "pulse_weight",
    "precision_weight",
    # Streaming features
    "EWEntropy",
    "EWEntropyConfig",
    "EWMomentum",
    "EWZScore",
    "EWSkewness",
    "ema_update",
    "ewvar_update",
]

_MODULE_EXPORTS: dict[str, tuple[str, ...]] = {
    "core.neuro.adapters.tradepulse_adapter": (
        "MarketPulse",
        "TradePulseNeuroAdapter",
    ),
    "core.neuro.advanced": (
        "AgencyControlNetwork",
        "CandidateGenerator",
        "DopaminePredictionNetwork",
        "ECANeuroTradingAdapter",
        "EnhancedFractalNeuroeconomicCore",
        "IntegratedNeuroTradingSystem",
        "MarketContext",
        "NeuroAdvancedConfig",
        "NeuroDecisionIntegrator",
        "NeuroplasticReinforcementEngine",
        "NeuroRiskManager",
        "NeuroStateMonitor",
        "TradeOutcome",
        "TradeResult",
    ),
    "core.neuro.amm": ("AdaptiveMarketMind", "AMMConfig"),
    "core.neuro.ecs_regulator": ("ECSInspiredRegulator", "ECSMetrics"),
    "core.neuro.features": (
        "EWEntropy",
        "EWEntropyConfig",
        "EWMomentum",
        "EWSkewness",
        "EWZScore",
        "ema_update",
        "ewvar_update",
    ),
    "core.neuro.fractal_regulator": ("EEPFractalRegulator", "RegulatorMetrics"),
    "core.neuro.motivation": (
        "FractalMotivationController",
        "FractalMotivationEngine",
        "MotivationDecision",
        "RealTimeMotivationMonitor",
    ),
    "core.neuro.quantile": ("ExactQuantile", "P2Algorithm", "P2Quantile"),
    "core.neuro.shocks": ("ShockScenario", "ShockScenarioGenerator"),
    "core.neuro.sizing": (
        "SizerConfig",
        "position_size",
        "kelly_size",
        "risk_parity_weight",
        "pulse_weight",
        "precision_weight",
    ),
    "core.neuro.training": (
        "AsyncDataLoader",
        "CheckpointManager",
        "MixedPrecisionContext",
        "ProfileSnapshot",
        "TrainingBatch",
        "TrainingComponent",
        "TrainingConfig",
        "TrainingEngine",
        "TrainingProfiler",
        "TrainingSample",
        "TrainingStepResult",
        "TrainingSummary",
    ),
}


def __getattr__(name: str) -> Any:
    """Lazily load neuro modules to avoid importing heavy dependencies at import time."""

    for module_name, exports in _MODULE_EXPORTS.items():
        if name in exports:
            module = importlib.import_module(module_name)
            value = getattr(module, name)
            globals()[name] = value
            return value
    raise AttributeError(f"module 'core.neuro' has no attribute '{name}'")
