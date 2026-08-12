# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""Tests for INV-COSMOLOGICAL-COMPUTE (P1, statistical, EXTRAPOLATED)."""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.physics.cosmological_compute_bound import (
    BH_BIT_COEFF,
    PLANCK_LENGTH_M,
    PROVENANCE_TIER,
    CausalDiamond,
    assess_compute_claim,
    diamond_compute_budget,
    holographic_bit_capacity,
)


def test_provenance_tier_is_extrapolated() -> None:
    """Provenance tier must be EXTRAPOLATED — useful-compute mapping is research."""
    assert PROVENANCE_TIER == "EXTRAPOLATED"


def test_holographic_bit_coefficient_finite() -> None:
    """BH_BIT_COEFF = 1 / (4 · ℓ_p² · ln 2) must be finite and positive."""
    assert math.isfinite(BH_BIT_COEFF)
    assert BH_BIT_COEFF > 0.0


def test_holographic_capacity_zero_area_is_zero_bits() -> None:
    """A = 0 ⇒ 0 bits (degenerate horizon)."""
    assert holographic_bit_capacity(0.0) == 0.0


def test_holographic_capacity_negative_area_raises() -> None:
    """Area is unsigned in this contract."""
    with pytest.raises(ValueError):
        holographic_bit_capacity(-1.0)


def test_holographic_capacity_non_finite_raises() -> None:
    """INV-HPC2: NaN / Inf area is fail-closed."""
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            holographic_bit_capacity(bad)


def test_holographic_capacity_planck_area_is_quarter_over_ln2() -> None:
    """A = ℓ_p² ⇒ I = 1/(4 · ln 2) bits ≈ 0.36 bits per Planck area."""
    bits = holographic_bit_capacity(PLANCK_LENGTH_M**2)
    expected = 1.0 / (4.0 * math.log(2.0))
    assert math.isclose(bits, expected, rel_tol=1e-12)


def test_holographic_capacity_solar_mass_horizon_order_of_magnitude() -> None:
    """1 M_sun BH (R_s ≈ 2954 m) ⇒ A ≈ 1.10e8 m² ⇒ I ≈ 1.5e77 bits."""
    radius_s = 2954.0
    area = 4.0 * math.pi * radius_s**2
    bits = holographic_bit_capacity(area)
    log10_bits = math.log10(bits)
    msg = f"solar-mass BH log10(bits)={log10_bits:.2f}, expected ∈ [76, 78]"
    assert 76.0 <= log10_bits <= 78.0, msg


def test_holographic_capacity_hubble_horizon_order_of_magnitude() -> None:
    """Hubble radius ~ 1.4e26 m ⇒ A ~ 2.5e53 m² ⇒ I ~ 10^122-123 bits.

    Order-of-magnitude consistent with widely-cited cosmological-horizon
    bit count of ~10^122 (e.g. Lloyd 2002, computational capacity of
    the universe).
    """
    hubble_radius = 1.4e26
    area = 4.0 * math.pi * hubble_radius**2
    bits = holographic_bit_capacity(area)
    log10_bits = math.log10(bits)
    msg = f"Hubble-horizon log10(bits)={log10_bits:.2f}, expected ∈ [121, 124]"
    assert 121.0 <= log10_bits <= 124.0, msg


def test_diamond_budget_returns_holographic_ceiling() -> None:
    """diamond_compute_budget reports the Bekenstein-Hawking ceiling."""
    d = CausalDiamond(horizon_area_m2=1.0)
    budget = diamond_compute_budget(d)
    assert math.isclose(budget.holographic_max_bits, BH_BIT_COEFF * 1.0, rel_tol=1e-12)


def test_compute_claim_within_budget() -> None:
    """Claim of half the holographic capacity is within budget."""
    d = CausalDiamond(horizon_area_m2=1.0)
    budget = diamond_compute_budget(d)
    half = budget.holographic_max_bits / 2.0
    witness = assess_compute_claim(d, half)
    assert witness.is_within_budget is True
    assert witness.reason is None


def test_compute_claim_at_exact_budget_within() -> None:
    """Saturation case — equality permitted."""
    d = CausalDiamond(horizon_area_m2=1.0)
    budget = diamond_compute_budget(d)
    witness = assess_compute_claim(d, budget.holographic_max_bits)
    assert witness.is_within_budget is True
    assert witness.margin_bits == 0.0


def test_compute_claim_above_budget_violation() -> None:
    """Claim above holographic ceiling violates INV-COSMOLOGICAL-COMPUTE."""
    d = CausalDiamond(horizon_area_m2=1.0)
    budget = diamond_compute_budget(d)
    over = budget.holographic_max_bits * 2.0
    witness = assess_compute_claim(d, over)
    assert witness.is_within_budget is False
    assert witness.reason is not None
    assert "INV-COSMOLOGICAL-COMPUTE" in witness.reason


def test_compute_claim_negative_or_non_finite_raises() -> None:
    """Negative or NaN claim is fail-closed."""
    d = CausalDiamond(horizon_area_m2=1.0)
    with pytest.raises(ValueError):
        assess_compute_claim(d, -1.0)
    with pytest.raises(ValueError):
        assess_compute_claim(d, float("nan"))


@given(
    area_m2=st.floats(min_value=0.0, max_value=1e60, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_property_holographic_capacity_linear_in_area(area_m2: float) -> None:
    """Property: I_max = BH_BIT_COEFF · A for any non-negative finite A."""
    bits = holographic_bit_capacity(area_m2)
    assert math.isclose(bits, BH_BIT_COEFF * area_m2, rel_tol=1e-10)
