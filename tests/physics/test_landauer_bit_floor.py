# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for ``landauer_bit_floor`` — the per-bit kT ln2 erasure floor.

Distinct from ``landauer_nonzero_erasure_cost`` (which only asserts the cost is
strictly *positive*) and from ``irreversible_cost_dominance`` (reversible vs
irreversible baseline). This law pins the *exact value* of the floor:

    Delta_F_erase(n bits) == n * k_B * T * ln 2   (Landauer 1961; INV-TAU2)

i.e. equality at the reversible floor, linear in temperature T, and any demand
to erase below kT ln 2 per bit is rejected fail-closed (proving the bound is
ENFORCED, not advisory). Both the floor value and its enforcement reuse the real
canonical functions — no constants are reimplemented here.
"""

from __future__ import annotations

import math

import pytest

# Real Landauer floor: cost = k_B * T * ln2 * bits (no reimplementation).
from core.physics.landauer import K_BOLTZMANN, bit_erasure_cost

# Real INV-TAU2 enforcement: a sub-Landauer initial-precision demand (erasing
# below the kT ln2 budget) is rejected as "physically unaffordable".
from core.physics.predictability_horizon import (
    landauer_min_initial_precision,
    predictability_horizon_under_budget,
)

_LN2 = math.log(2.0)
# Temperature sweep spanning cryogenic -> hot baths (kelvin).
_TEMPERATURES = (4.2, 77.0, 300.0, 600.0, 1000.0)
# Per-bit equality is machine-exact: the floor IS k_B*T*ln2*bits.
_REL_TOL = 1e-12


def test_per_bit_erasure_floor_equals_kT_ln2() -> None:
    """Positive witness: erasure cost == n * k_B*T*ln2 (>=, equality at floor).

    Across a temperature sweep and several bit counts the measured per-bit floor
    equals k_B*T*ln2 to machine tolerance, never dips below it, and scales
    linearly in T (floor/T is constant).
    """
    per_kelvin = bit_erasure_cost(1.0, 1.0)  # k_B * ln2 (the slope in T)
    for temperature in _TEMPERATURES:
        expected_one_bit = K_BOLTZMANN * temperature * _LN2
        for bits in (1.0, 8.0, 1024.0):
            cost = bit_erasure_cost(bits, temperature)
            expected = bits * expected_one_bit
            ratio = cost / expected
            assert cost >= expected * (1.0 - _REL_TOL), (
                f"LANDAUER-BIT-FLOOR VIOLATED: cost {cost:.6e} < floor "
                f"{expected:.6e} for {bits} bits at T={temperature} K. "
                f"Law: Delta_F_erase >= n*k_B*T*ln2 (Landauer 1961, INV-TAU2). "
                f"Measured floor/(n*k_B*T*ln2) ratio = {ratio:.17f}. "
                f"There is no sub-kT-ln2 erasure of information."
            )
            assert abs(ratio - 1.0) <= _REL_TOL, (
                f"LANDAUER-BIT-FLOOR VIOLATED: cost {cost:.6e} != reversible "
                f"floor {expected:.6e} for {bits} bits at T={temperature} K. "
                f"Law: Delta_F_erase == n*k_B*T*ln2 at the reversible floor "
                f"(Landauer 1961, INV-TAU2). ratio = {ratio:.17f} (tol {_REL_TOL:.0e}). "
                f"The per-bit floor must be exact, not approximate."
            )
        # Linear in T: floor(T)/T equals the single-kelvin slope k_B*ln2.
        slope = bit_erasure_cost(1.0, temperature) / temperature
        assert abs(slope / per_kelvin - 1.0) <= _REL_TOL, (
            f"LANDAUER-BIT-FLOOR VIOLATED: floor/T {slope:.6e} != k_B*ln2 "
            f"{per_kelvin:.6e} at T={temperature} K. "
            f"Law: the kT ln2 floor is LINEAR in temperature (Landauer 1961, "
            f"INV-TAU2). Ratio {slope / per_kelvin:.17f} (tol {_REL_TOL:.0e}). "
            f"A non-linear floor would break the conservation accounting."
        )


def test_sub_landauer_erasure_is_rejected() -> None:
    """Negative control: a sub-kT-ln2 erasure demand and invalid T fail closed.

    (1) A one-bit energy budget (E = k_B*T*ln2) affords exactly one bit of
        precision (delta_0_min = Delta/2). Demanding delta_0 below that floor —
        i.e. erasing below the kT ln2 budget — is rejected "physically
        unaffordable" (INV-TAU2). This proves the bound is ENFORCED, not
        advisory.
    (2) An undefined thermal context (T <= 0 or non-finite) fails closed.
    """
    dynamic_range = 1.0
    temperature = 300.0
    one_bit_budget = bit_erasure_cost(1.0, temperature)  # exactly k_B*T*ln2
    floor_precision = landauer_min_initial_precision(
        one_bit_budget, dynamic_range=dynamic_range, T_kelvin=temperature
    )
    # One-bit budget affords exactly one bit: delta_0_min == Delta/2.
    assert abs(floor_precision - dynamic_range / 2.0) <= _REL_TOL, (
        f"LANDAUER-BIT-FLOOR setup invalid: one-bit budget afforded precision "
        f"{floor_precision} != Delta/2 = {dynamic_range / 2.0}."
    )
    # Demanding precision below the floor = erasing below kT ln2 => rejected.
    with pytest.raises(ValueError, match="physically unaffordable"):
        predictability_horizon_under_budget(
            1.0,
            delta_tol=0.9,
            dynamic_range=dynamic_range,
            energy_budget_J=one_bit_budget,
            T_kelvin=temperature,
            delta_0_request=floor_precision / 2.0,
        )
    # Invalid thermal context fails closed (no silent floor of 0).
    for bad_temperature in (0.0, -1.0, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="temperature must be finite and > 0"):
            bit_erasure_cost(1.0, bad_temperature)
