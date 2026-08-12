# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Public indicator exports for convenient access in tests and notebooks.

Loading is lazy (PEP 562): importing a leaf numerical module such as
``core.indicators.temporal_ricci`` or ``core.indicators.ricci`` must NOT drag in
the data/IO layer (pydantic, cryptography) through eager package re-exports.
Names below resolve to their submodule on first attribute access, so
``from core.indicators import TemporalRicciAnalyzer`` keeps working while
``import core.indicators.temporal_ricci`` stays importable with only
``numpy/scipy/pandas/networkx`` installed.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

# attribute name -> submodule (relative, without leading dot)
_EXPORTS: dict[str, str] = {
    # cache
    "BackfillState": "cache",
    "CacheRecord": "cache",
    "FileSystemIndicatorCache": "cache",
    "cache_indicator": "cache",
    "hash_input_data": "cache",
    "make_fingerprint": "cache",
    # ensemble_divergence
    "EnsembleDivergenceResult": "ensemble_divergence",
    "IndicatorDivergenceSignal": "ensemble_divergence",
    "compute_ensemble_divergence": "ensemble_divergence",
    # flow_metrics
    "FMN_DEFAULT_WEIGHTS": "flow_metrics",
    "QILM_DEFAULT_EPS": "flow_metrics",
    "compute_fmn": "flow_metrics",
    "compute_qilm": "flow_metrics",
    # hierarchical_features
    "FeatureBufferCache": "hierarchical_features",
    "HierarchicalFeatureResult": "hierarchical_features",
    "TimeFrameSpec": "hierarchical_features",
    "compute_hierarchical_features": "hierarchical_features",
    # kuramoto
    "KuramotoOrderFeature": "kuramoto",
    "MultiAssetKuramotoFeature": "kuramoto",
    "compute_phase": "kuramoto",
    "compute_phase_gpu": "kuramoto",
    "kuramoto_order": "kuramoto",
    "multi_asset_kuramoto": "kuramoto",
    # kuramoto_ricci_composite
    "GeoSyncCompositeEngine": "kuramoto_ricci_composite",
    "KuramotoRicciComposite": "kuramoto_ricci_composite",
    "MarketPhase": "kuramoto_ricci_composite",
    # market_state_contract
    "EntryState": "market_state_contract",
    "MarketRegime": "market_state_contract",
    "MarketStateContract": "market_state_contract",
    "compile_market_state": "market_state_contract",
    # multiscale_kuramoto
    "KuramotoResult": "multiscale_kuramoto",
    "MultiScaleKuramoto": "multiscale_kuramoto",
    "MultiScaleKuramotoFeature": "multiscale_kuramoto",
    "MultiScaleResult": "multiscale_kuramoto",
    "TimeFrame": "multiscale_kuramoto",
    "WaveletWindowSelector": "multiscale_kuramoto",
    # normalization
    "IndicatorNormalizationConfig": "normalization",
    "IndicatorNormalizer": "normalization",
    "NormalizationMode": "normalization",
    "normalize_indicator_series": "normalization",
    "resolve_indicator_normalizer": "normalization",
    # phase_entry_gate
    "DEFAULT_PHASE_ENTRY_CONFIG": "phase_entry_gate",
    "GateConditions": "phase_entry_gate",
    "GateReading": "phase_entry_gate",
    "PhaseEntryGate": "phase_entry_gate",
    "PhaseEntryGateConfig": "phase_entry_gate",
    "Signal": "phase_entry_gate",
    # pipeline
    "IndicatorPipeline": "pipeline",
    "PipelineResult": "pipeline",
    # pivot_detection
    "DivergenceClass": "pivot_detection",
    "DivergenceKind": "pivot_detection",
    "PivotDivergenceSignal": "pivot_detection",
    "PivotPoint": "pivot_detection",
    "detect_pivot_divergences": "pivot_detection",
    "detect_pivots": "pivot_detection",
    # temporal_ricci
    "TemporalRicciAnalyzer": "temporal_ricci",
    # trading
    "HurstIndicator": "trading",
    "KuramotoIndicator": "trading",
    "VPINIndicator": "trading",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f".{module_name}", __name__)
    value = getattr(module, name)
    globals()[name] = value  # cache so subsequent access skips __getattr__
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))


if TYPE_CHECKING:  # eager names for static analysers / IDEs only.
    # Redundant ``as`` aliases mark these as intentional re-exports (ruff/mypy).
    from .cache import BackfillState as BackfillState
    from .cache import CacheRecord as CacheRecord
    from .cache import FileSystemIndicatorCache as FileSystemIndicatorCache
    from .cache import cache_indicator as cache_indicator
    from .cache import hash_input_data as hash_input_data
    from .cache import make_fingerprint as make_fingerprint
    from .ensemble_divergence import EnsembleDivergenceResult as EnsembleDivergenceResult
    from .ensemble_divergence import IndicatorDivergenceSignal as IndicatorDivergenceSignal
    from .ensemble_divergence import compute_ensemble_divergence as compute_ensemble_divergence
    from .flow_metrics import FMN_DEFAULT_WEIGHTS as FMN_DEFAULT_WEIGHTS
    from .flow_metrics import QILM_DEFAULT_EPS as QILM_DEFAULT_EPS
    from .flow_metrics import compute_fmn as compute_fmn
    from .flow_metrics import compute_qilm as compute_qilm
    from .hierarchical_features import FeatureBufferCache as FeatureBufferCache
    from .hierarchical_features import HierarchicalFeatureResult as HierarchicalFeatureResult
    from .hierarchical_features import TimeFrameSpec as TimeFrameSpec
    from .hierarchical_features import (
        compute_hierarchical_features as compute_hierarchical_features,
    )
    from .kuramoto import KuramotoOrderFeature as KuramotoOrderFeature
    from .kuramoto import MultiAssetKuramotoFeature as MultiAssetKuramotoFeature
    from .kuramoto import compute_phase as compute_phase
    from .kuramoto import compute_phase_gpu as compute_phase_gpu
    from .kuramoto import kuramoto_order as kuramoto_order
    from .kuramoto import multi_asset_kuramoto as multi_asset_kuramoto
    from .kuramoto_ricci_composite import GeoSyncCompositeEngine as GeoSyncCompositeEngine
    from .kuramoto_ricci_composite import KuramotoRicciComposite as KuramotoRicciComposite
    from .kuramoto_ricci_composite import MarketPhase as MarketPhase
    from .market_state_contract import EntryState as EntryState
    from .market_state_contract import MarketRegime as MarketRegime
    from .market_state_contract import MarketStateContract as MarketStateContract
    from .market_state_contract import compile_market_state as compile_market_state
    from .multiscale_kuramoto import KuramotoResult as KuramotoResult
    from .multiscale_kuramoto import MultiScaleKuramoto as MultiScaleKuramoto
    from .multiscale_kuramoto import MultiScaleKuramotoFeature as MultiScaleKuramotoFeature
    from .multiscale_kuramoto import MultiScaleResult as MultiScaleResult
    from .multiscale_kuramoto import TimeFrame as TimeFrame
    from .multiscale_kuramoto import WaveletWindowSelector as WaveletWindowSelector
    from .normalization import IndicatorNormalizationConfig as IndicatorNormalizationConfig
    from .normalization import IndicatorNormalizer as IndicatorNormalizer
    from .normalization import NormalizationMode as NormalizationMode
    from .normalization import normalize_indicator_series as normalize_indicator_series
    from .normalization import resolve_indicator_normalizer as resolve_indicator_normalizer
    from .phase_entry_gate import DEFAULT_PHASE_ENTRY_CONFIG as DEFAULT_PHASE_ENTRY_CONFIG
    from .phase_entry_gate import GateConditions as GateConditions
    from .phase_entry_gate import GateReading as GateReading
    from .phase_entry_gate import PhaseEntryGate as PhaseEntryGate
    from .phase_entry_gate import PhaseEntryGateConfig as PhaseEntryGateConfig
    from .phase_entry_gate import Signal as Signal
    from .pipeline import IndicatorPipeline as IndicatorPipeline
    from .pipeline import PipelineResult as PipelineResult
    from .pivot_detection import DivergenceClass as DivergenceClass
    from .pivot_detection import DivergenceKind as DivergenceKind
    from .pivot_detection import PivotDivergenceSignal as PivotDivergenceSignal
    from .pivot_detection import PivotPoint as PivotPoint
    from .pivot_detection import detect_pivot_divergences as detect_pivot_divergences
    from .pivot_detection import detect_pivots as detect_pivots
    from .temporal_ricci import TemporalRicciAnalyzer as TemporalRicciAnalyzer
    from .trading import HurstIndicator as HurstIndicator
    from .trading import KuramotoIndicator as KuramotoIndicator
    from .trading import VPINIndicator as VPINIndicator
