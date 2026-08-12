# SPDX-License-Identifier: MIT
from __future__ import annotations

UNIT_STATE = {
    "theta": "radian",
    "omega": "radian_per_time",
    "K": "inverse_time",
    "A": "dimensionless",
    "R": "dimensionless",
    "Phi": "inverse_time",
    "dt": "time",
}

EQUATION_UNITS = {
    "kuramoto_rhs": ("radian_per_time", ("radian_per_time", "inverse_time")),
    "order_parameter": ("dimensionless", ("dimensionless",)),
    "margin_phi": ("inverse_time", ("inverse_time", "inverse_time")),
}


def test_kuramoto_rhs_terms_are_dimensionally_homogeneous() -> None:
    """NON_PHYSICS: static unit-label bookkeeping contract.

    Compares hardcoded unit-label strings in a documentation dict; it computes
    no physical quantity and cannot falsify the engine's math (it passes
    regardless of whether the RHS is correct). Not a physics-invariant witness.
    """
    units = {
        "dtheta_dt": "rad/time",
        "omega": "rad/time",
        "K": "1/time",
        "A": "dimensionless",
        "sin_delta_theta": "dimensionless",
    }
    coupling_term = "1/time"
    assert units["dtheta_dt"] == units["omega"]
    assert coupling_term == "1/time"


def test_boundary_phi_terms_are_dimensionally_homogeneous() -> None:
    """NON_PHYSICS: static unit-label bookkeeping contract.

    Asserts equality of hardcoded unit-label strings for the Φ boundary; no
    physical quantity is computed and no physics bug can be caught.
    """
    units = {
        "K": "1/time",
        "lambda_max_A": "dimensionless",
        "gamma": "1/time",
        "Phi": "1/time",
    }
    assert units["K"] == units["gamma"] == units["Phi"]
    assert units["lambda_max_A"] == "dimensionless"


def test_critical_coupling_unit_matches_K() -> None:
    """NON_PHYSICS: static unit-label bookkeeping contract.

    Compares hardcoded unit-label strings for K_c; no quantity is computed,
    so it cannot falsify the critical-coupling formula. Not a physics witness.
    """
    unit_gamma = "1/time"
    unit_lambda = "dimensionless"
    unit_K = "1/time"
    assert unit_lambda == "dimensionless"
    assert unit_gamma == unit_K


def test_unit_state_contract_is_complete() -> None:
    """NON_PHYSICS: completeness check on a static unit-label dict (no physics)."""
    assert set(UNIT_STATE) == {"theta", "omega", "K", "A", "R", "Phi", "dt"}
    assert UNIT_STATE["theta"] == "radian"
    assert UNIT_STATE["A"] == "dimensionless"
    assert UNIT_STATE["R"] == "dimensionless"


def test_equation_unit_contract_is_complete() -> None:
    """NON_PHYSICS: completeness check on a static equation-unit dict (no physics)."""
    assert set(EQUATION_UNITS) == {"kuramoto_rhs", "order_parameter", "margin_phi"}
    assert EQUATION_UNITS["kuramoto_rhs"] == (
        "radian_per_time",
        ("radian_per_time", "inverse_time"),
    )
    assert EQUATION_UNITS["margin_phi"] == (
        "inverse_time",
        ("inverse_time", "inverse_time"),
    )
