# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync protocol primitives.

This package collects the core abstractions that back the unified
Div/Conv-driven GeoSync protocol.  The goal is to keep the public
interfaces lightweight while providing mathematically precise building
blocks that downstream services can rely on.
"""

__CANONICAL__ = True

from .divconv import (
    DivConvSignal,
    DivConvSnapshot,
    aggregate_signals,
    compute_divergence_functional,
    compute_kappa,
    compute_price_gradient,
    compute_theta,
    compute_threshold_tau_c,
    compute_threshold_tau_d,
    compute_time_warp_invariant_metric,
)

__all__ = [
    "DivConvSignal",
    "DivConvSnapshot",
    "aggregate_signals",
    "compute_divergence_functional",
    "compute_kappa",
    "compute_price_gradient",
    "compute_theta",
    "compute_threshold_tau_c",
    "compute_threshold_tau_d",
    "compute_time_warp_invariant_metric",
]
