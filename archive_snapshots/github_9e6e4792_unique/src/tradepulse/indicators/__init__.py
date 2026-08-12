# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""TradePulse indicators module - Re-exports from core.indicators for public API.

This module provides convenient access to all indicator classes and functions
through the tradepulse namespace, as documented in the README.

Example:
    >>> from tradepulse.indicators import MultiscaleKuramoto
    >>> analyzer = MultiscaleKuramoto()
    >>> result = analyzer.analyze(df)
"""

__CANONICAL__ = True

from core.indicators import (
    BackfillState,
    CacheRecord,
    DivergenceClass,
    DivergenceKind,
    EnsembleDivergenceResult,
    FeatureBufferCache,
    FileSystemIndicatorCache,
    HierarchicalFeatureResult,
    HurstIndicator,
    IndicatorDivergenceSignal,
    IndicatorNormalizationConfig,
    IndicatorNormalizer,
    IndicatorPipeline,
    KuramotoIndicator,
    KuramotoOrderFeature,
    KuramotoResult,
    KuramotoRicciComposite,
    MarketPhase,
    MultiAssetKuramotoFeature,
    MultiScaleKuramoto,
    MultiScaleKuramotoFeature,
    MultiScaleResult,
    NormalizationMode,
    PipelineResult,
    PivotDivergenceSignal,
    PivotPoint,
    TemporalRicciAnalyzer,
    TimeFrame,
    TimeFrameSpec,
    TradePulseCompositeEngine,
    VPINIndicator,
    WaveletWindowSelector,
    cache_indicator,
    compute_ensemble_divergence,
    compute_hierarchical_features,
    compute_phase,
    compute_phase_gpu,
    detect_pivot_divergences,
    detect_pivots,
    hash_input_data,
    kuramoto_order,
    make_fingerprint,
    multi_asset_kuramoto,
    normalize_indicator_series,
    resolve_indicator_normalizer,
)

# Alias for README compatibility
MultiscaleKuramoto = MultiScaleKuramoto

__all__ = [
    # Kuramoto indicators
    "compute_phase",
    "compute_phase_gpu",
    "kuramoto_order",
    "multi_asset_kuramoto",
    "KuramotoOrderFeature",
    "MultiAssetKuramotoFeature",
    "KuramotoIndicator",
    # Multi-scale Kuramoto
    "KuramotoResult",
    "MultiScaleKuramoto",
    "MultiscaleKuramoto",
    "MultiScaleKuramotoFeature",
    "MultiScaleResult",
    "TimeFrame",
    "WaveletWindowSelector",
    # Kuramoto-Ricci composite
    "KuramotoRicciComposite",
    "MarketPhase",
    "TradePulseCompositeEngine",
    # Ensemble divergence
    "compute_ensemble_divergence",
    "IndicatorDivergenceSignal",
    "EnsembleDivergenceResult",
    # Hierarchical features
    "FeatureBufferCache",
    "HierarchicalFeatureResult",
    "TimeFrameSpec",
    "compute_hierarchical_features",
    # Pipeline and caching
    "IndicatorPipeline",
    "PipelineResult",
    "BackfillState",
    "CacheRecord",
    "FileSystemIndicatorCache",
    "cache_indicator",
    "hash_input_data",
    "make_fingerprint",
    # Normalization
    "IndicatorNormalizer",
    "IndicatorNormalizationConfig",
    "NormalizationMode",
    "normalize_indicator_series",
    "resolve_indicator_normalizer",
    # Pivot detection
    "PivotPoint",
    "PivotDivergenceSignal",
    "DivergenceClass",
    "DivergenceKind",
    "detect_pivots",
    "detect_pivot_divergences",
    # Temporal analysis
    "TemporalRicciAnalyzer",
    # Trading indicators
    "HurstIndicator",
    "VPINIndicator",
]
