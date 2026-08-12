# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic synthetic L2 order-book generator.

Public surface
--------------
``synthesize_l2_snapshot``
    Build a single :class:`core.kuramoto.capital_weighted.L2DepthSnapshot`.
``synthesize_l2_stream``
    Build a temporal sequence of snapshots with optional regime drift.
``RegimeSpec``
    Custom regime parameters container.
``uniform_depth`` / ``pareto_depth`` / ``winner_takes_most_depth`` /
``bimodal_depth``
    Low-level depth-mass samplers (re-exported for advanced callers).

This package contains *no real exchange data* and never opens a network
socket. Use it for tests, benchmarks, and research validation only.
"""

from __future__ import annotations

from .book_factory import (
    MidPriceDistribution,
    RegimeName,
    RegimeSpec,
    synthesize_l2_snapshot,
)
from .regimes import (
    bimodal_depth,
    pareto_depth,
    uniform_depth,
    winner_takes_most_depth,
)
from .streams import synthesize_l2_stream

__all__ = [
    "MidPriceDistribution",
    "RegimeName",
    "RegimeSpec",
    "bimodal_depth",
    "pareto_depth",
    "synthesize_l2_snapshot",
    "synthesize_l2_stream",
    "uniform_depth",
    "winner_takes_most_depth",
]
