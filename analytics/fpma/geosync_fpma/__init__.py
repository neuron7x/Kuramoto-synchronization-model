# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Standalone public API for the GeoSync FPMA model."""

from analytics.fpma.src.adapters.local import (
    FilePersistence,
    InMemoryPersistence,
    LocalOptimizer,
    LocalRiskModel,
    LocalSum,
)
from analytics.fpma.src.core import (
    FractalPortfolioAnalyzer,
    FractalWeights,
    MarketRegime,
    RegimeSnapshot,
    add,
    compute_hurst_exponent,
    detect_regime,
    wavelet_decomposition,
)
from analytics.fpma.src.ports.ports import (
    DataRetrievalPort,
    OptimizationPort,
    PersistencePort,
    RiskModelPort,
    SumPort,
)

__all__ = [
    "FractalPortfolioAnalyzer",
    "FractalWeights",
    "MarketRegime",
    "DataRetrievalPort",
    "FilePersistence",
    "InMemoryPersistence",
    "LocalOptimizer",
    "LocalRiskModel",
    "LocalSum",
    "OptimizationPort",
    "PersistencePort",
    "RegimeSnapshot",
    "RiskModelPort",
    "SumPort",
    "add",
    "compute_hurst_exponent",
    "detect_regime",
    "wavelet_decomposition",
]
