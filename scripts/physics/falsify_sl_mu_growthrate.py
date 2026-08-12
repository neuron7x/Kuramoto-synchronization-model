# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsifier for the Stuart-Landau μ growth-rate estimator (Scientific Debt A3).

Feeds a known STABLE (exponentially decaying-envelope) synthetic oscillator into
``core.physics.stuart_landau_es`` and exits non-zero iff the estimated linear
growth rate μ ≥ 0. A stable focus has a decaying amplitude envelope, so a
first-principles growth-rate estimator MUST return μ < 0. The prior fabricated
map ``tanh(variance/var_max − 0.5)`` had no link to a growth rate and would not
reliably satisfy this; the OLS-log-amplitude-slope estimator does.

Exit codes:
    0  μ < 0 on every asset (estimator tracks a real decay rate)
    1  μ ≥ 0 anywhere (fabrication / sign failure)
    2  non-finite μ or runtime error
"""

from __future__ import annotations

import sys

import numpy as np
from numpy.typing import NDArray

from core.physics.stuart_landau_es import _extract_amplitude_phase_omega


def _stable_decaying_prices(
    rate: float = -0.05,
    n_t: int = 96,
    n_assets: int = 4,
    freq: float = 0.8,
    amp0: float = 0.01,
    seed: int = 7,
) -> NDArray[np.float64]:
    """Price panel whose log-return envelope decays at ``rate`` < 0 (stable focus)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_t - 1, dtype=np.float64)
    env = np.exp(rate * t)
    log_rets = np.empty((n_t - 1, n_assets), dtype=np.float64)
    for j in range(n_assets):
        log_rets[:, j] = amp0 * env * np.sin(freq * t + j) + rng.standard_normal(n_t - 1) * 1e-5
    prices: NDArray[np.float64] = np.empty((n_t, n_assets), dtype=np.float64)
    prices[0, :] = 100.0
    prices[1:, :] = 100.0 * np.exp(np.cumsum(log_rets, axis=0))
    return prices


def main() -> int:
    prices = _stable_decaying_prices()
    try:
        _, _, _, mu = _extract_amplitude_phase_omega(prices)
    except (
        ValueError,
        FloatingPointError,
        ZeroDivisionError,
        RuntimeError,
        np.linalg.LinAlgError,
    ) as exc:
        print(f"FALSIFIER ERROR: estimator raised: {exc!r}")
        return 2
    if not np.all(np.isfinite(mu)):
        print(f"FALSIFIER FAIL: non-finite μ = {mu}")
        return 2
    mu_max = float(mu.max())
    if mu_max >= 0.0:
        print(
            "FALSIFIER FAIL: stable decaying oscillator produced "
            f"max μ = {mu_max:.6e} ≥ 0; μ must be < 0 for a stable focus. "
            f"per-asset μ = {mu.tolist()}"
        )
        return 1
    print(f"FALSIFIER PASS: stable decaying oscillator → μ < 0 (max μ = {mu_max:.6e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
