"""Neuroscience-inspired modules for TradePulse."""

from .adapters.tradepulse_adapter import MarketPulse, TradePulseNeuroAdapter
from .advanced import (
    AgencyControlNetwork,
    CandidateGenerator,
    DopaminePredictionNetwork,
    ECANeuroTradingAdapter,
    EnhancedFractalNeuroeconomicCore,
    IntegratedNeuroTradingSystem,
    MarketContext,
    NeuroAdvancedConfig,
    NeuroDecisionIntegrator,
    NeuroplasticReinforcementEngine,
    NeuroRiskManager,
    NeuroStateMonitor,
    TradeOutcome,
    TradeResult,
)
from .amm import AdaptiveMarketMind, AMMConfig
from .ecs_regulator import ECSInspiredRegulator, ECSMetrics
from .features import (
    EWEntropy,
    EWEntropyConfig,
    EWMomentum,
    EWSkewness,
    EWZScore,
    ema_update,
    ewvar_update,
)
from .fractal_regulator import EEPFractalRegulator, RegulatorMetrics
from .motivation import (
    FractalMotivationController,
    FractalMotivationEngine,
    MotivationDecision,
    RealTimeMotivationMonitor,
)
from .quantile import ExactQuantile, P2Algorithm, P2Quantile
from .shocks import ShockScenario, ShockScenarioGenerator
from .sizing import (
    SizerConfig,
    kelly_size,
    position_size,
    precision_weight,
    pulse_weight,
    risk_parity_weight,
)
from .training import (
    AsyncDataLoader,
    CheckpointManager,
    MixedPrecisionContext,
    ProfileSnapshot,
    TrainingBatch,
    TrainingComponent,
    TrainingConfig,
    TrainingEngine,
    TrainingProfiler,
    TrainingSample,
    TrainingStepResult,
    TrainingSummary,
)

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
