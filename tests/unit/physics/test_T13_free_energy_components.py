# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T13 — Free-energy component non-negativity witness for INV-FE2.

The Helmholtz-style free energy computed by
``core.physics.free_energy_trading_gate.FreeEnergyTradingGate.check``
takes the form

    F = U − T·S

where U is a risk exposure proxy (Σ|pos|·|ret|), T is the order-book
temperature, and S is a Tsallis entropy. F itself is unbounded below
and can legitimately be negative for diversified portfolios at high
temperature — that is why the original "F ≥ 0" statement of INV-FE2
was wrong and has been rewritten as a component-level bound.

What this witness enforces is the physical admissibility of each
building block on every gate check:

* U ≥ 0 — risk exposure is a sum of absolute values.
* T ≥ 0 — temperature is a positive intensive variable.
* S ≥ 0 — Tsallis entropy for q > 1 is non-negative on any
  normalised weight distribution.

A single violation in any component indicates a bug in the
corresponding subroutine (risk_exposure, compute_T_LOB, or
tsallis_entropy), not a fluctuation in the composite F.
"""

from __future__ import annotations

import numpy as np

from core.physics.free_energy_trading_gate import FreeEnergyTradingGate


def test_free_energy_components_stay_non_negative_across_gate_sweep() -> None:
    """INV-FE2: U, T, S each ≥ 0 on every decision across a 40-scenario sweep.

    Drives the FreeEnergyTradingGate with 40 seeded-random (before, after,
    returns) triples spanning diversified, concentrated, low-vol and
    high-vol regimes. For every decision, asserts each component of F is
    non-negative. The numerical floor is an epsilon of 1e-12 to absorb
    ULPs from the Tsallis entropy sum.
    """
    rng = np.random.default_rng(seed=101)
    gate = FreeEnergyTradingGate(T_base=0.60, q=1.5, vol_reference=0.01)
    n_scenarios = 40
    component_floor_epsilon = 1e-12  # ULP tolerance from Tsallis sum

    for scenario_idx in range(n_scenarios):
        n_assets = int(rng.integers(low=2, high=8))
        pos_before = rng.uniform(low=0.0, high=10.0, size=n_assets)
        pos_after = rng.uniform(low=0.0, high=10.0, size=n_assets)
        returns = rng.uniform(low=-0.05, high=0.05, size=n_assets)

        decision = gate.check(
            positions_before=pos_before,
            positions_after=pos_after,
            recent_returns=returns,
        )

        assert decision.U_before >= -component_floor_epsilon, (
            f"INV-FE2 VIOLATED on scenario={scenario_idx}: "
            f"U_before={decision.U_before:.6e} < 0. "
            f"Expected risk exposure Σ|pos|·|ret| ≥ 0 by definition. "
            f"Observed at N={n_assets} assets, T_base=0.60, q=1.5, seed=101. "
            f"Physical reasoning: U is a sum of non-negative products; "
            f"negative U means compute_risk_exposure drifted."
        )
        assert decision.U_after >= -component_floor_epsilon, (
            f"INV-FE2 VIOLATED on scenario={scenario_idx}: "
            f"U_after={decision.U_after:.6e} < 0. "
            f"Expected risk exposure Σ|pos|·|ret| ≥ 0 by definition. "
            f"Observed at N={n_assets} assets, T_base=0.60, q=1.5, seed=101. "
            f"Physical reasoning: U is a sum of non-negative products."
        )
        assert decision.T_LOB >= -component_floor_epsilon, (
            f"INV-FE2 VIOLATED on scenario={scenario_idx}: "
            f"T_LOB={decision.T_LOB:.6e} < 0. "
            f"Expected order-book temperature ≥ 0 as an intensive variable. "
            f"Observed at N={n_assets} assets, T_base=0.60, q=1.5, seed=101. "
            f"Physical reasoning: temperature is a positive intensive "
            f"variable by construction (fallback to realized_volatility is "
            f"clamped non-negative)."
        )
        assert decision.S_q_before >= -component_floor_epsilon, (
            f"INV-FE2 VIOLATED on scenario={scenario_idx}: "
            f"S_q_before={decision.S_q_before:.6e} < 0. "
            f"Expected Tsallis entropy ≥ 0 for q=1.5 on any weight dist. "
            f"Observed at N={n_assets} assets, T_base=0.60, q=1.5, seed=101. "
            f"Physical reasoning: for q > 1, S_q = (1 − Σ p^q)/(q − 1) ≥ 0 "
            f"because Σp^q ≤ 1 on normalised probability vectors."
        )
        assert decision.S_q_after >= -component_floor_epsilon, (
            f"INV-FE2 VIOLATED on scenario={scenario_idx}: "
            f"S_q_after={decision.S_q_after:.6e} < 0. "
            f"Expected Tsallis entropy ≥ 0 for q=1.5 on any weight dist. "
            f"Observed at N={n_assets} assets, T_base=0.60, q=1.5, seed=101. "
            f"Physical reasoning: for q > 1, S_q = (1 − Σ p^q)/(q − 1) ≥ 0."
        )
