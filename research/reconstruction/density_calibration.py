# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Density calibration + GATE_3 enforcement.

Per Protocol X-10R:

    GATE_3  DENSITY_BOUND          INVALIDATE
        - 0.01 ≤ inferred_density ≤ 0.15
        - density > 0.15 → complete-graph regime, Kuramoto R
          trivially saturates; precursor undetectable
        - density < 0.01 → disconnected regime, R undefined
        - both → ReconstructionStatus.OUT_OF_DENSITY_BOUND
"""

from __future__ import annotations

import numpy as np

from research.reconstruction.cimini_squartini import (
    HiddenFitness,
    fit_cimini_squartini,
    p_link,
)

DENSITY_LOWER: float = 0.01
DENSITY_UPPER: float = 0.15
DEFAULT_TARGET_DENSITY: float = 0.05


def inferred_density(fit: HiddenFitness) -> float:
    """Edge density implied by the calibrated p_ij matrix."""
    n = fit.x.shape[0]
    p = p_link(fit.x, fit.y, fit.z)
    return float(p.sum() / (n * (n - 1)))


def calibrate_density_z(
    s_out: np.ndarray,
    s_in: np.ndarray,
    *,
    target_density: float = DEFAULT_TARGET_DENSITY,
) -> HiddenFitness:
    """Calibrate the global z parameter to hit the target density.

    Returns a ``HiddenFitness`` with z chosen so that
    ``inferred_density(fit) ≈ target_density`` to within ~1e-9.
    Caller is responsible for downstream GATE_3 check.
    """
    if not (0.0 < target_density < 1.0):
        raise ValueError(f"target_density must be in (0, 1); got {target_density}")
    return fit_cimini_squartini(s_out, s_in, target_density=target_density)


def density_bound_passes(density: float) -> bool:
    """GATE_3 — return True iff density ∈ [DENSITY_LOWER, DENSITY_UPPER]."""
    return DENSITY_LOWER <= density <= DENSITY_UPPER
