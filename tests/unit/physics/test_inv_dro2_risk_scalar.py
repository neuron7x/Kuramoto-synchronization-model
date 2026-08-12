# SPDX-License-Identifier: MIT
"""INV-DRO2 — risk_scalar bound and Lipschitz-1 properties.

INV-DRO2 (universal, P0): ``rs = max(0, 1 - |γ - 1|) ∈ [0, 1]``.
Lipschitz-1 in γ. Fail-closed on regimes ≠ CRITICAL/TRANS.

The companion catalog test file
(`tests/unit/physics/test_T_dro1_gamma_algebraic.py`, currently on
PR #517) covers the algebraic identity ``γ = 2H + 1``. This file
covers the *boundedness* and *Lipschitz* properties of the risk
scalar that consumes ``γ``.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.dro_ara.engine import risk_scalar


@pytest.mark.parametrize(
    ("gamma", "expected"),
    [
        (1.0, 1.0),  # peak: |γ−1| = 0
        (0.0, 0.0),  # |γ−1| = 1 ⟹ rs = max(0, 0) = 0
        (2.0, 0.0),  # symmetric counterpart of γ = 0
        (1.5, 0.5),
        (0.5, 0.5),
        (1.25, 0.75),
        (0.75, 0.75),
        (-100.0, 0.0),  # extreme negative — clipped at 0
        (100.0, 0.0),  # extreme positive — clipped at 0
    ],
)
def test_inv_dro2_risk_scalar_canonical_values(gamma: float, expected: float) -> None:
    """INV-DRO2: rs(γ) matches max(0, 1 − |γ − 1|) at canonical points.

    Property-style: each parametrized point is checked against the closed
    form, and a local γ-grid around the point is swept to confirm the
    formula holds for *every* sampled input, not just the canonical value.
    """
    rs = risk_scalar(gamma)
    assert rs == pytest.approx(expected, abs=1e-6), (
        f"INV-DRO2 VIOLATED at γ={gamma}: rs={rs!r} != expected={expected!r}. "
        f"Formula: max(0, 1 − |γ − 1|). Round-tripped to 6 decimals. "
        "Physical reasoning: risk scalar peaks at γ=1 (white-noise regime), "
        "drops linearly to zero at |γ−1|=1, and is hard-floored at zero "
        "elsewhere — fail-closed clamp on the lower bound."
    )
    for offset in (-0.2, -0.05, 0.05, 0.2):
        g = gamma + offset
        rs_g = risk_scalar(g)
        closed_form = max(0.0, 1.0 - abs(g - 1.0))
        assert rs_g == pytest.approx(closed_form, abs=1e-6), (
            f"INV-DRO2 VIOLATED at γ={g}: rs={rs_g!r} != "
            f"max(0, 1 − |γ − 1|)={closed_form!r}; the closed form must hold "
            f"for every γ, not only canonical points. base γ={gamma}."
        )


@given(gamma=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_inv_dro2_property_bounded_in_unit_interval(gamma: float) -> None:
    """INV-DRO2 universal: rs(γ) ∈ [0, 1] for any finite γ."""
    rs = risk_scalar(gamma)
    assert 0.0 <= rs <= 1.0, (
        f"INV-DRO2 VIOLATED: rs={rs!r} out of [0, 1] at γ={gamma}. "
        "Physical reasoning: rs is a scaled clip; any escape outside "
        "the unit interval implies the max(0, ·) or the implicit "
        "upper bound at γ=1 has been corrupted."
    )


@given(
    g1=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    g2=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_inv_dro2_property_lipschitz_one(g1: float, g2: float) -> None:
    """INV-DRO2 Lipschitz-1: |rs(g1) − rs(g2)| ≤ |g1 − g2| + ε.

    The function ``max(0, 1 − |γ − 1|)`` is the composition of
    Lipschitz-1 maps (absolute value, 1−·, max with constant), so
    its Lipschitz constant is 1. Round-tripping to 6 decimals can
    add up to 5e-7 of slack on each call; accept 2·5e-7 = 1e-6.
    """
    rounding_slack = 1e-6
    delta_rs = abs(risk_scalar(g1) - risk_scalar(g2))
    delta_g = abs(g1 - g2)
    assert delta_rs <= delta_g + rounding_slack, (
        f"INV-DRO2 LIPSCHITZ VIOLATED: observed |Δrs| = {delta_rs:.6e}, must "
        f"satisfy |Δrs| ≤ |Δγ| = {delta_g:.6e} + slack {rounding_slack:.0e}. "
        f"At g1={g1}, g2={g2}, rs1={risk_scalar(g1)}, rs2={risk_scalar(g2)}. "
        "Physical reasoning: rs is a Lipschitz-1 composition; a slope >1 "
        "implies the max(·) or the abs(·) has drifted from its definition."
    )


def test_inv_dro2_finite_gamma_yields_finite_rs() -> None:
    """INV-DRO2: finite-input ⟹ finite-output (companion to INV-HPC2)."""
    for g in [-100.0, -1.0, 0.0, 0.5, 1.0, 1.5, 2.0, 100.0]:
        rs = risk_scalar(g)
        assert math.isfinite(rs), (
            f"INV-DRO2 / INV-HPC2 VIOLATED: at g={g} observed rs={rs!r} "
            "non-finite. Pure clip arithmetic on a finite input must yield a "
            "finite output; non-finite output implies a numeric pathology in "
            "the rounding or the clip."
        )


def test_inv_dro2_peak_at_unity() -> None:
    """INV-DRO2: rs attains its supremum 1.0 only at γ = 1.0.

    Property-style: the peak value is checked at γ=1 and every off-peak
    sample on a neighborhood grid must be strictly below it, witnessing
    that γ=1 is the unique maximiser of max(0, 1 − |γ − 1|).
    """
    rs_at_one = risk_scalar(1.0)
    peak = 1.0  # closed-form supremum of max(0, 1 − |γ − 1|)
    assert rs_at_one == peak, (
        f"INV-DRO2 PEAK VIOLATED: observed rs at gamma=1.0 is {rs_at_one!r}, "
        f"must equal {peak}. |γ − 1| = 0 at γ = 1 ⟹ rs = max(0, 1) = 1 "
        "exactly; any value < 1 implies a sign or rounding drift."
    )
    off_peak = [risk_scalar(g) for g in (0.4, 0.7, 0.95, 1.05, 1.3, 1.6)]
    assert all(rs < rs_at_one for rs in off_peak), (
        f"INV-DRO2 PEAK VIOLATED: observed off-peak rs values {off_peak} must "
        f"all be strictly below the supremum at gamma=1.0 ({rs_at_one}); rs is "
        "strictly unimodal in γ with its unique maximum at γ = 1."
    )
