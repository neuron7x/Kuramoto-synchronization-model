# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""INV-K2 witness: subcritical Kuramoto coupling decays toward incoherence."""

from __future__ import annotations

import numpy as np

from core.kuramoto import KuramotoConfig, run_simulation


def test_inv_k2_subcritical_order_parameter_decays() -> None:
    """INV-K2: K << K_c implies R(t→∞) < ε with finite-size tolerance ε=3/sqrt(N)."""
    n = 200
    sigma_omega = 1.0
    k_c_mf = 2 * sigma_omega / np.pi
    k_subcritical = 0.3 * k_c_mf
    epsilon = 3.0 / np.sqrt(n)

    config = KuramotoConfig(
        N=n,
        K=k_subcritical,
        dt=0.01,
        steps=3000,
        seed=42,
    )
    result = run_simulation(config)
    r_final = float(result.order_parameter[-1])

    assert r_final < epsilon, (
        f"INV-K2 violated: K={k_subcritical:.4f} < K_c={k_c_mf:.4f}, "
        f"but R_final={r_final:.4f} >= ε={epsilon:.4f} (n={n})."
    )
