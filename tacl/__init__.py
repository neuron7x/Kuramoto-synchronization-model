"""Thermodynamic Autonomic Control Layer (TACL) utilities.

Enhanced v2.0.0 with advanced diagnostics, optimization, and monitoring.
"""

from .behavioral_contract import (
    BehavioralContract,
    BehavioralContractReport,
    BehavioralContractViolation,
    ContractBreach,
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
from .energy_diagnostics import (
    AnomalyReport,
    EnergyBreakdown,
    EnergyBudget,
    EnergyDiagnostics,
    EnergyTrend,
    EntropyDecomposition,
)
from .energy_optimization import (
    AdaptiveWeightTuner,
    AnnealingSchedule,
    GradientDescentOptimizer,
    OptimizationResult,
    PhaseTransitionDetector,
    SimulatedAnnealingOptimizer,
)
from .energy_monitoring import (
    AlertSeverity,
    EnergyAlert,
    EnergyMonitor,
    EnergyReporter,
    PrometheusMetrics,
)
from .validate import load_scenarios

__all__ = [
    # Core energy model
    "DEFAULT_THRESHOLDS",
    "DEFAULT_WEIGHTS",
    "EnergyMetrics",
    "EnergyModel",
    "EnergyValidationError",
    "EnergyValidationResult",
    "EnergyValidator",
    # Behavioral contracts
    "BehavioralContract",
    "BehavioralContractReport",
    "BehavioralContractViolation",
    "ContractBreach",
    # Diagnostics
    "AnomalyReport",
    "EnergyBreakdown",
    "EnergyBudget",
    "EnergyDiagnostics",
    "EnergyTrend",
    "EntropyDecomposition",
    # Optimization
    "AdaptiveWeightTuner",
    "AnnealingSchedule",
    "GradientDescentOptimizer",
    "OptimizationResult",
    "PhaseTransitionDetector",
    "SimulatedAnnealingOptimizer",
    # Monitoring
    "AlertSeverity",
    "EnergyAlert",
    "EnergyMonitor",
    "EnergyReporter",
    "PrometheusMetrics",
    # Utilities
    "load_scenarios",
]
