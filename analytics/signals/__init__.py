"""Signal research utilities for feature engineering and model evaluation."""

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
from .irreversibility import (
    IGSConfig,
    IGSMetrics,
    StreamingIGS,
    compute_igs_features,
    igs_directional_signal,
)
from .irreversibility_adapter import IGSFeatureProvider

__all__ = [
    "FeaturePipelineConfig",
    "LeakageGate",
    "ModelCandidate",
    "SignalFeaturePipeline",
    "SignalModelEvaluation",
    "SignalModelSelector",
    "build_supervised_learning_frame",
    "make_default_candidates",
    "IGSConfig",
    "IGSMetrics",
    "StreamingIGS",
    "compute_igs_features",
    "igs_directional_signal",
    "IGSFeatureProvider",
]
