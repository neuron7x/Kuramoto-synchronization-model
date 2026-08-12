# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witness for the HPC numerical-stability law.

Binds a pytest function to the catalog law ``hpc.numerical_stability`` via
``@law`` and proves it holds for the ``geosync_hpc.evaluation`` numerical
kernels (an allowed import):

* ``hpc.numerical_stability`` (INV-HPC2) — finite inputs within the documented
  range produce finite outputs; no NaN/Inf is synthesized. The witness drives
  the sharpe / cvar / max_drawdown / deflated_sharpe kernels with finite return
  and equity series spanning nine orders of magnitude, plus the zero-variance
  edge, and requires every output to be finite.

Nothing here is a market claim. These are finite-in / finite-out facts about the
performance kernels.
"""

from __future__ import annotations

import math

import numpy as np

from geosync_hpc.evaluation import cvar, deflated_sharpe, max_drawdown, sharpe
from physics_contracts.law import law


@law("hpc.numerical_stability", n_scales=6, series_length=500)
def test_kernels_keep_finite_inputs_finite() -> None:
    """INV-HPC2: finite inputs produce finite kernel outputs (no NaN/Inf).

    For finite return and equity series across nine orders of magnitude — and the
    degenerate zero-variance return series — every performance kernel must return
    a finite value. A single NaN/Inf would mean the kernel synthesized a
    non-finite output from finite, in-range data.
    """
    series_length = 500
    scales = (1e-8, 1e-3, 1.0, 1e3, 1e6, 1e9)
    rng = np.random.default_rng(seed=0)
    non_finite = 0
    checks = 0
    for scale in scales:
        returns = rng.normal(0.0, scale, size=series_length)
        equity = 100.0 + np.cumsum(rng.normal(0.0, scale, size=series_length))
        outputs = (
            sharpe(returns),
            cvar(returns),
            max_drawdown(equity),
            deflated_sharpe(float(sharpe(returns)), series_length),
        )
        for value in outputs:
            checks += 1
            if not math.isfinite(float(value)):
                non_finite += 1
    # Zero-variance edge: a constant return series must still yield a finite Sharpe.
    constant_returns = np.full(series_length, 0.01)
    checks += 1
    if not math.isfinite(float(sharpe(constant_returns))):
        non_finite += 1
    assert non_finite == 0, (
        "INV-HPC2 violated: observed non_finite outputs = "
        f"{non_finite} of checks={checks} with seed=0 and series_length={series_length} must "
        "be 0; finite in-range inputs must never produce NaN/Inf"
    )
