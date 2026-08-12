# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync indicators module - Re-exports from core.indicators for public API.

This module provides convenient access to all indicator classes and functions
through the geosync namespace, as documented in the README.

Example:
    >>> from geosync.indicators import MultiscaleKuramoto
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
    EntryState,
    FeatureBufferCache,
    FileSystemIndicatorCache,
    GeoSyncCompositeEngine,
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
    MarketRegime,
    MarketStateContract,
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
    VPINIndicator,
    WaveletWindowSelector,
    cache_indicator,
    compile_market_state,
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
    "GeoSyncCompositeEngine",
    # Market-state compiler contract
    "MarketStateContract",
    "MarketRegime",
    "EntryState",
    "compile_market_state",
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
