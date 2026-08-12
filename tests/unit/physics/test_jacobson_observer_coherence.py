# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""Tests for INV-JACOBSON-OBSERVER (P1, conditional, EXTRAPOLATED)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.physics.jacobson_observer_coherence import (
    PROVENANCE_TIER,
    ClausiusContext,
    assess_jacobson_observer,
    clausius_residual,
)


def test_provenance_tier_is_extrapolated() -> None:
    """Provenance tier must be EXTRAPOLATED — Jacobson 1995 settled,
    observer-coherence extension is research direction."""
    assert PROVENANCE_TIER == "EXTRAPOLATED"


def test_pure_jacobson_satisfied_when_dQ_equals_T_dS() -> None:
    """Pure Jacobson recovery: δQ = T·dS, c = 0 ⇒ residual = 0."""
    ctx = ClausiusContext(
        heat_flow_J=10.0,
        unruh_temperature_K=2.0,
        entropy_change_J_per_K=5.0,
    )
    assert clausius_residual(ctx) == 0.0


def test_pure_jacobson_violated_when_dQ_neq_T_dS() -> None:
    """δQ ≠ T·dS, c = 0 ⇒ non-zero residual indicates non-thermal horizon."""
    ctx = ClausiusContext(
        heat_flow_J=10.0,
        unruh_temperature_K=2.0,
        entropy_change_J_per_K=4.0,  # T·dS = 8, residual = 2
    )
    assert clausius_residual(ctx) == 2.0


def test_extended_residual_includes_observer_correction() -> None:
    """residual = δQ - T·dS - c."""
    ctx = ClausiusContext(
        heat_flow_J=10.0,
        unruh_temperature_K=2.0,
        entropy_change_J_per_K=5.0,
        observer_coherence_correction_J=3.0,
    )
    assert clausius_residual(ctx) == -3.0


def test_witness_pure_jacobson_consistent_when_residual_below_tol() -> None:
    """Default tol 1e-30 J: small residuals at machine precision are OK."""
    ctx = ClausiusContext(
        heat_flow_J=10.0,
        unruh_temperature_K=2.0,
        entropy_change_J_per_K=5.0,
    )
    w = assess_jacobson_observer(ctx)
    assert w.is_pure_jacobson_consistent is True
    assert w.is_extended_consistent is True
    assert w.reason is None


def test_witness_extended_inconsistent_when_correction_breaks_balance() -> None:
    """Pure Jacobson holds but c introduces a non-zero residual ⇒
    extended inconsistent; reason explains."""
    ctx = ClausiusContext(
        heat_flow_J=10.0,
        unruh_temperature_K=2.0,
        entropy_change_J_per_K=5.0,
        observer_coherence_correction_J=1.0,
    )
    w = assess_jacobson_observer(ctx)
    assert w.is_pure_jacobson_consistent is True
    assert w.is_extended_consistent is False
    assert w.reason is not None
    assert "INV-JACOBSON-OBSERVER" in w.reason


def test_witness_pure_inconsistent_when_input_is_not_thermal_horizon() -> None:
    """Input where δQ ≠ T·dS (and c=0) ⇒ pure-Jacobson inconsistent."""
    ctx = ClausiusContext(
        heat_flow_J=10.0,
        unruh_temperature_K=2.0,
        entropy_change_J_per_K=4.0,
    )
    w = assess_jacobson_observer(ctx)
    assert w.is_pure_jacobson_consistent is False
    assert w.is_extended_consistent is False
    assert w.reason is not None


def test_decoupled_limit_recovers_jacobson() -> None:
    """As c → 0, extended residual → pure residual (no observer effect)."""
    base_ctx = ClausiusContext(
        heat_flow_J=10.0,
        unruh_temperature_K=2.0,
        entropy_change_J_per_K=5.0,
    )
    base_residual = clausius_residual(base_ctx)
    for tiny_c in (1e-40, 1e-50, 0.0):
        ctx = ClausiusContext(
            heat_flow_J=10.0,
            unruh_temperature_K=2.0,
            entropy_change_J_per_K=5.0,
            observer_coherence_correction_J=tiny_c,
        )
        # As c shrinks, residual approaches pure residual.
        assert abs(clausius_residual(ctx) - base_residual) <= max(tiny_c, 1e-40)


def test_negative_unruh_temperature_raises() -> None:
    """T < 0 is unphysical for a thermal horizon — fail-closed."""
    with pytest.raises(ValueError):
        clausius_residual(
            ClausiusContext(
                heat_flow_J=10.0,
                unruh_temperature_K=-1.0,
                entropy_change_J_per_K=5.0,
            )
        )


def test_non_finite_inputs_raise() -> None:
    """INV-HPC2: NaN / Inf in any field is fail-closed."""
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            clausius_residual(
                ClausiusContext(
                    heat_flow_J=bad,
                    unruh_temperature_K=2.0,
                    entropy_change_J_per_K=5.0,
                )
            )


def test_witness_dataclass_is_frozen() -> None:
    """JacobsonObserverWitness is immutable post-construction."""
    ctx = ClausiusContext(
        heat_flow_J=0.0,
        unruh_temperature_K=0.0,
        entropy_change_J_per_K=0.0,
    )
    w = assess_jacobson_observer(ctx)
    with pytest.raises(AttributeError):
        w.is_pure_jacobson_consistent = False  # type: ignore[misc]


def test_negative_tolerance_raises() -> None:
    ctx = ClausiusContext(
        heat_flow_J=0.0,
        unruh_temperature_K=0.0,
        entropy_change_J_per_K=0.0,
    )
    with pytest.raises(ValueError):
        assess_jacobson_observer(ctx, tolerance_J=-1.0)


@given(
    dQ=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    T=st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    dS=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    c=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
)
def test_property_residual_equals_dQ_minus_T_dS_minus_c(
    dQ: float, T: float, dS: float, c: float
) -> None:
    """Property: clausius_residual = δQ - T·dS - c for any finite inputs."""
    ctx = ClausiusContext(
        heat_flow_J=dQ,
        unruh_temperature_K=T,
        entropy_change_J_per_K=dS,
        observer_coherence_correction_J=c,
    )
    expected = dQ - T * dS - c
    assert clausius_residual(ctx) == pytest.approx(expected, rel=1e-10, abs=1e-10)
