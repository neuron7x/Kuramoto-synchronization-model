# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witness for the thermodynamic Landauer-floor law in the catalog.

Binds the catalog law ``thermo.landauer_bound`` to an executable ``@law`` witness
and proves it holds in the real ``core.physics.landauer.LandauerInferenceProfiler``:

* ``thermo.landauer_bound`` — per-bit information erasure costs exactly the
  Landauer floor E_bit = k_B·T·ln 2, and the N-bit minimum E_min(N) = N·E_bit is
  a hard additive lower bound, N-bit cost ≥ N·k_B·T·ln 2 (INV-TH3).

The floor is a first-principles constant (Landauer 1961): it depends only on the
Boltzmann constant and the temperature proxy T, never on any market quantity.
Nothing here is a market claim — these are thermodynamic-contract facts about the
erasure-cost kernel.
"""

from __future__ import annotations

import math

from core.physics.landauer import K_BOLTZMANN, LandauerInferenceProfiler
from physics_contracts.law import law

# Per-bit identity is exact to float precision (both sides evaluate k_B·T·ln 2).
IDENTITY_TOLERANCE = 1e-30
# Temperatures (K) the floor is checked at — spans cryogenic to hot reservoirs.
TEMPERATURES = (1.0, 77.0, 300.0, 1000.0)
# Bit counts for the additive N-bit floor check.
BIT_COUNTS = (0, 1, 2, 8, 64, 4096)


@law("thermo.landauer_bound", n_temperatures=4, n_bit_counts=6)
def test_landauer_per_bit_identity_and_additive_floor() -> None:
    """INV-TH3: per-bit cost == k_B·T·ln 2 and N-bit cost ≥ N·k_B·T·ln 2.

    For every temperature proxy T the profiler's ``landauer_per_bit`` must equal
    the first-principles floor k_B·T·ln 2 to float precision, and ``minimum_energy``
    must never fall below the additive N-bit floor N·k_B·T·ln 2 for any bit count.
    The witness sweeps temperatures and bit counts and tracks the worst excursions.
    """
    n_temperatures = len(TEMPERATURES)
    n_bit_counts = len(BIT_COUNTS)
    worst_identity_error = 0.0
    worst_floor_deficit = 0.0
    for temperature in TEMPERATURES:
        profiler = LandauerInferenceProfiler(T=temperature)
        expected_per_bit = K_BOLTZMANN * temperature * math.log(2.0)
        worst_identity_error = max(
            worst_identity_error, abs(profiler.landauer_per_bit - expected_per_bit)
        )
        for n_bits in BIT_COUNTS:
            floor = n_bits * expected_per_bit
            deficit = floor - profiler.minimum_energy(n_bits)
            worst_floor_deficit = max(worst_floor_deficit, deficit)

    assert worst_identity_error <= IDENTITY_TOLERANCE, (
        "INV-TH3 violated: observed worst |E_bit − k_B·T·ln 2| = "
        f"{worst_identity_error:.2e} must be ≤ {IDENTITY_TOLERANCE:.0e} "
        f"with n_temperatures={n_temperatures}; the per-bit cost must equal the Landauer floor exactly"
    )
    assert worst_floor_deficit <= IDENTITY_TOLERANCE, (
        "INV-TH3 violated: observed worst (N·E_bit − minimum_energy(N)) = "
        f"{worst_floor_deficit:.2e} must be ≤ {IDENTITY_TOLERANCE:.0e} "
        f"with n_bit_counts={n_bit_counts}; the N-bit cost must never fall below the additive floor"
    )
