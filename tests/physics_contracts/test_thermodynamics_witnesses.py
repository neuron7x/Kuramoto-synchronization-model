# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witnesses for the thermodynamics laws in the physics catalog.

Each binds a pytest function to a first-principles catalog law via ``@law`` and
proves it holds in the real ``core.physics`` code, deriving every tolerance from
the law. Two previously-unwitnessed laws gain witnesses:

* ``thermo.second_law_closed``   — entropy of a closed subsystem is
  non-decreasing under coarse-graining / mixing (INV-TH2).
* ``thermo.free_energy_descent`` — the free-energy trading gate admits a
  position change only when the free energy F = U − T·S does not increase
  (INV-FE1).

Nothing here is a market claim. These are thermodynamics facts about the code.
"""

from __future__ import annotations

import math

import numpy as np

from core.physics.free_energy_trading_gate import FreeEnergyTradingGate
from core.physics.thermodynamics import boltzmann_entropy
from physics_contracts.law import law

# Catalog ``thermo.second_law_closed`` slack: S(t+1) − S(t) ≥ −1e-12.
ENTROPY_SLACK = 1e-12
# Catalog ``thermo.free_energy_descent``: the gate's admit boundary is ΔF ≤ 0,
# so only float round-off is allowed on an admitted trade.
FREE_ENERGY_SLACK = 1e-9


@law("thermo.second_law_closed", n_distributions=40, mixing_fractions=(0.1, 0.3, 0.6))
def test_entropy_non_decreasing_under_mixing() -> None:
    """INV-TH2: a closed-subsystem mixing step never lowers Boltzmann entropy.

    Relaxation toward the uniform distribution, p ← (1−λ)p + λ·u, is a
    doubly-stochastic map; by concavity of S = −k_B Σ p ln p it cannot decrease
    entropy. The witness sweeps random distributions and mixing fractions and
    tracks the worst-case ΔS, which must stay non-negative within bit-level slack.
    """
    n_distributions = 40
    mixing_fractions = (0.1, 0.3, 0.6)
    rng = np.random.default_rng(seed=0)
    worst_delta_s = math.inf
    for _ in range(n_distributions):
        size = int(rng.integers(4, 10))
        p = rng.dirichlet(np.ones(size))
        uniform = np.ones(size) / size
        s_before = boltzmann_entropy(p)
        for lam in mixing_fractions:
            p_mixed = (1.0 - lam) * p + lam * uniform
            delta_s = boltzmann_entropy(p_mixed) - s_before
            worst_delta_s = min(worst_delta_s, delta_s)
    assert worst_delta_s >= -ENTROPY_SLACK, (
        "INV-TH2 violated: observed worst ΔS = "
        f"{worst_delta_s:.3e} must be ≥ −{ENTROPY_SLACK:.0e} under mixing over "
        f"n_distributions={n_distributions} with seed=0; entropy cannot decrease "
        "under a doubly-stochastic relaxation of a closed subsystem"
    )


@law("thermo.free_energy_descent", n_trades=200, temperature=1.0)
def test_free_energy_gate_admits_only_descent() -> None:
    """INV-FE1: the gate admits a position change only when F is non-increasing.

    The free-energy trading gate computes F = U − T·S for the before/after
    positions and sets ``allowed = (ΔF ≤ 0)``. The witness drives the gate with
    random position changes and checks two things: the admit flag agrees with the
    sign of ΔF, and no admitted trade increases free energy. Any admitted ΔF > 0
    is a violation of the descent law.
    """
    n_trades = 200
    temperature = 1.0
    gate = FreeEnergyTradingGate()
    rng = np.random.default_rng(seed=0)
    violations = 0
    flag_disagreements = 0
    worst_admitted_delta_f = -math.inf
    for _ in range(n_trades):
        size = int(rng.integers(2, 6))
        positions_before = rng.normal(0.0, 1.0, size)
        positions_after = rng.normal(0.0, 1.0, size)
        recent_returns = rng.normal(0.0, 0.02, size)
        decision = gate.check(
            positions_before, positions_after, recent_returns, T_LOB=temperature
        )
        if decision.allowed != (decision.delta_F <= FREE_ENERGY_SLACK):
            flag_disagreements += 1
        if decision.allowed:
            worst_admitted_delta_f = max(worst_admitted_delta_f, decision.delta_F)
            if decision.delta_F > FREE_ENERGY_SLACK:
                violations += 1
    assert flag_disagreements == 0, (
        "INV-FE1 violated: observed flag_disagreements = "
        f"{flag_disagreements} must be 0 over n_trades={n_trades} with seed=0; the "
        "gate's admit flag must equal sign(ΔF ≤ 0)"
    )
    assert violations == 0, (
        "INV-FE1 violated: observed violations = "
        f"{violations} admitted trades with ΔF > {FREE_ENERGY_SLACK:.0e} (worst "
        f"admitted ΔF = {worst_admitted_delta_f:.3e}) over n_trades={n_trades} with "
        "seed=0; an admitted trade must never increase free energy"
    )
