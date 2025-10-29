"""Signal research utilities for feature engineering and model evaluation."""

from .convergence import (
    ConvergenceConfig,
    ConvergenceDetector,
    ConvergenceScores,
    compute_convergence,
    is_convergent,
)
from .irreversibility import (
    IGSConfig,
    IGSMetrics,
    RollingPermutationEntropy,
    RollingTRA,
    StreamingIGS,
    ZScoreQuantizer,
    compute_igs_features,
    igs_directional_signal,
)
from .irreversibility_adapter import IGSFeatureProvider
from .pipeline import (
    FeaturePipelineConfig,
    LeakageGate,
    ModelCandidate,
    SignalFeaturePipeline,
    SignalModelEvaluation,
    SignalModelSelector,
    build_supervised_learning_frame,
    make_default_candidates,
)

__all__ = [
    "FeaturePipelineConfig",
    "LeakageGate",
    "ModelCandidate",
    "SignalFeaturePipeline",
    "SignalModelEvaluation",
    "SignalModelSelector",
    "build_supervised_learning_frame",
    "make_default_candidates",
    "ConvergenceConfig",
    "ConvergenceDetector",
    "ConvergenceScores",
    "compute_convergence",
    "is_convergent",
    "IGSConfig",
    "IGSMetrics",
    "RollingPermutationEntropy",
    "RollingTRA",
    "StreamingIGS",
    "ZScoreQuantizer",
    "compute_igs_features",
    "igs_directional_signal",
    "IGSFeatureProvider",
]
