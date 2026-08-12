# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Signal research utilities for feature engineering and model evaluation."""

from __future__ import annotations

from importlib import import_module
from typing import Any

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
from .news_sentiment import (
    FinBERTSentimentModel,
    NewsArticle,
    NewsCollector,
    NewsSentimentModel,
    NewsSentimentPipeline,
    SentimentLabel,
    aggregate_sentiment,
)

_PIPELINE_EXPORTS = {
    "FeaturePipelineConfig",
    "LeakageGate",
    "ModelCandidate",
    "SignalFeaturePipeline",
    "SignalModelEvaluation",
    "SignalModelSelector",
    "build_supervised_learning_frame",
    "make_default_candidates",
}


def __getattr__(name: str) -> Any:
    if name not in _PIPELINE_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(".pipeline", package=__name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


__all__ = [
    "FeaturePipelineConfig",
    "LeakageGate",
    "ModelCandidate",
    "SignalFeaturePipeline",
    "SignalModelEvaluation",
    "SignalModelSelector",
    "build_supervised_learning_frame",
    "make_default_candidates",
    "NewsArticle",
    "NewsCollector",
    "NewsSentimentModel",
    "NewsSentimentPipeline",
    "FinBERTSentimentModel",
    "SentimentLabel",
    "aggregate_sentiment",
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
