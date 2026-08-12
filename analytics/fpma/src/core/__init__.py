# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Core FPMA exports."""

from .main import (
    FractalPortfolioAnalyzer,
    FractalWeights,
    MarketRegime,
    RegimeSnapshot,
    add,
    compute_hurst_exponent,
    detect_regime,
    wavelet_decomposition,
)

__all__ = [
    "FractalPortfolioAnalyzer",
    "FractalWeights",
    "MarketRegime",
    "RegimeSnapshot",
    "add",
    "compute_hurst_exponent",
    "detect_regime",
    "wavelet_decomposition",
]
