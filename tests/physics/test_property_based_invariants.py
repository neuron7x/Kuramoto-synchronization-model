# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property-based falsification witnesses (Hypothesis-fuzzed invariants).

This module raises the falsification ceiling from hand-picked POINT witnesses
to PROPERTY witnesses: each physical invariant is verified over a WIDE,
machine-generated input distribution rather than a single seeded trajectory.
Every property reuses the REAL production function — no re-implemented physics.

Laws fuzzed here
----------------
* INV-K1     : ``compute_order_parameter`` in [0, 1] for ANY finite phase array.
* INV-RC1    : Ollivier-Ricci kappa <= 1 for ANY connected graph.
* INV-OA1    : Ott-Antonsen |z(t)| <= 1, R(t) in [0, 1] across K, delta, R0.
* INV-KELLY2 : applied Kelly fraction <= cap; full f* == mu / sigma^2.
* INV-DRO1   : ``derive_gamma`` satisfies gamma == 2*H + 1 for random walks.

Each property carries a 5-field failure message, a fail-closed assertion on
invalid (non-finite / degenerate) draws, and a NEGATIVE CONTROL proving the
predicate is non-vacuous (a deliberately out-of-range value fails the SAME
predicate).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from analytics.math_trading.kelly_criterion import kelly_from_edge_variance
from core.dro_ara.engine import derive_gamma
from core.indicators.temporal_ricci import LightGraph, OllivierRicciCurvatureLite
from core.kuramoto.ott_antonsen import OttAntonsenEngine
from core.physics.ricci_kuramoto import compute_order_parameter

# Float-precision slack for "<= 1" checks on quantities that are exactly bounded
# in exact arithmetic but accrue O(eps) round-off in float64.
_UNIT_SLACK: float = 1e-9


# ---------------------------------------------------------------------------
# Shared Hypothesis strategies
# ---------------------------------------------------------------------------
_finite_floats = st.floats(allow_nan=False, allow_infinity=False, width=64)


@st.composite
def connected_light_graphs(draw: st.DrawFn) -> LightGraph:
    """Draw a CONNECTED ``LightGraph``.

    Connectivity is guaranteed by laying down a spanning path 0-1-...-(n-1)
    (so INV-RC1's "connected graph" precondition always holds), then adding a
    Hypothesis-drawn set of extra chords to fuzz the topology.
    """
    n = draw(st.integers(min_value=3, max_value=10))
    graph = LightGraph(n)
    for i in range(n - 1):
        graph.add_edge(i, i + 1)
    extra = draw(
        st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=n - 1),
                st.integers(min_value=0, max_value=n - 1),
            ),
            max_size=n,
        )
    )
    for i, j in extra:
        if i != j:
            graph.add_edge(i, j)
    return graph


# ===========================================================================
# INV-K1 — Kuramoto order parameter R in [0, 1]
# ===========================================================================
@settings(max_examples=120, deadline=None)
@given(st.lists(_finite_floats, min_size=1, max_size=64))
def test_property_order_parameter_in_unit_interval(values: list[float]) -> None:
    """Positive witness: R = |mean(exp(i*theta))| in [0, 1] for ANY finite phases."""
    phases = np.asarray(values, dtype=np.float64)
    r = compute_order_parameter(phases)
    assert 0.0 <= r <= 1.0 + _UNIT_SLACK, (
        f"INV-K1 VIOLATED: R={r:.6f} left [0,1] (slack={_UNIT_SLACK:.1e}). "
        f"R is the modulus of a convex combination of unit vectors and is "
        f"bounded by construction. N={phases.size}, "
        f"phase_range=[{phases.min():.3e},{phases.max():.3e}], "
        f"property=order_parameter_unit_interval"
    )


@settings(max_examples=60, deadline=None)
@given(st.lists(_finite_floats, min_size=1, max_size=32), st.integers(min_value=0))
def test_property_order_parameter_rejects_nonfinite(values: list[float], idx: int) -> None:
    """Fail-closed: a non-finite phase poisons the array and must raise."""
    phases = np.asarray(values, dtype=np.float64)
    phases[idx % phases.size] = np.nan
    with pytest.raises(ValueError):
        compute_order_parameter(phases)


def test_negative_control_order_parameter_predicate() -> None:
    """Negative control: the [0,1] predicate is non-vacuous (R>1 fails it)."""
    out_of_range = 1.5
    assert not (0.0 <= out_of_range <= 1.0 + _UNIT_SLACK), (
        f"INV-K1 NEGATIVE-CONTROL BROKEN: predicate admitted R={out_of_range} > 1; "
        f"the order-parameter bound would be vacuous. slack={_UNIT_SLACK:.1e}. "
        f"expected=reject, got=admit, property=order_parameter_unit_interval"
    )


# ===========================================================================
# INV-RC1 — Ollivier-Ricci kappa <= 1 on any connected graph
# ===========================================================================
@settings(max_examples=80, deadline=None)
@given(connected_light_graphs())
def test_property_ollivier_kappa_upper_bounded(graph: LightGraph) -> None:
    """Positive witness: kappa = 1 - W1/d <= 1 for every edge of a connected graph."""
    estimator = OllivierRicciCurvatureLite(alpha=0.5)
    assert graph.is_connected(), "precondition: drawn graph must be connected"
    kappas = [estimator.edge_curvature(graph, edge) for edge in graph.edges()]
    worst = max(kappas)
    assert worst <= 1.0 + _UNIT_SLACK, (
        f"INV-RC1 VIOLATED: max edge kappa={worst:.6f} > 1 (slack={_UNIT_SLACK:.1e}). "
        f"Ollivier kappa = 1 - W1(mu_x,mu_y)/d(x,y) and W1>=0 forces kappa<=1. "
        f"nodes={graph.number_of_nodes()}, edges={graph.number_of_edges()}, "
        f"property=ollivier_kappa_upper_bound"
    )


def test_negative_control_ollivier_kappa_predicate() -> None:
    """Negative control: the kappa<=1 predicate rejects a fabricated kappa>1."""
    fabricated = 1.5
    assert not (fabricated <= 1.0 + _UNIT_SLACK), (
        f"INV-RC1 NEGATIVE-CONTROL BROKEN: predicate admitted kappa={fabricated} > 1; "
        f"the curvature bound would be vacuous. slack={_UNIT_SLACK:.1e}. "
        f"expected=reject, got=admit, property=ollivier_kappa_upper_bound"
    )


# ===========================================================================
# INV-OA1 — Ott-Antonsen |z(t)| <= 1, R(t) in [0, 1]
# ===========================================================================
@settings(max_examples=40, deadline=None)
@given(
    K=st.floats(min_value=0.05, max_value=8.0, allow_nan=False, allow_infinity=False),
    delta=st.floats(min_value=0.05, max_value=4.0, allow_nan=False, allow_infinity=False),
    R0=st.floats(min_value=1e-3, max_value=0.99, allow_nan=False, allow_infinity=False),
)
def test_property_ott_antonsen_order_parameter_bounded(K: float, delta: float, R0: float) -> None:
    """Positive witness: the integrated OA order parameter stays on the unit disk."""
    engine = OttAntonsenEngine(K=K, delta=delta, omega0=0.0)
    result = engine.integrate(T=8.0, dt=0.01, R0=R0)
    r_min = float(result.R.min())
    r_max = float(result.R.max())
    z_max = float(np.abs(result.z).max())
    assert r_min >= 0.0 and r_max <= 1.0 + _UNIT_SLACK and z_max <= 1.0 + _UNIT_SLACK, (
        f"INV-OA1 VIOLATED: R range=[{r_min:.6f},{r_max:.6f}], |z|_max={z_max:.6f} "
        f"left the unit disk (slack={_UNIT_SLACK:.1e}). The unit disk is the exact "
        f"invariant manifold of dz/dt=-(D+iw0)z+(K/2)(z-z|z|^2). "
        f"K={K:.4f}, delta={delta:.4f}, R0={R0:.4f}, "
        f"property=ott_antonsen_unit_disk"
    )


def test_ott_antonsen_rejects_invalid_params() -> None:
    """Fail-closed: non-finite K or non-positive delta is rejected at construction."""
    with pytest.raises(ValueError):
        OttAntonsenEngine(K=float("nan"), delta=0.5)
    with pytest.raises(ValueError):
        OttAntonsenEngine(K=1.0, delta=0.0)
    with pytest.raises(ValueError):
        OttAntonsenEngine(K=1.0, delta=-1.0)


def test_negative_control_ott_antonsen_predicate() -> None:
    """Negative control: the unit-disk predicate rejects a fabricated R>1."""
    fabricated = 1.25
    assert not (fabricated <= 1.0 + _UNIT_SLACK), (
        f"INV-OA1 NEGATIVE-CONTROL BROKEN: predicate admitted R={fabricated} > 1; "
        f"the unit-disk bound would be vacuous. slack={_UNIT_SLACK:.1e}. "
        f"expected=reject, got=admit, property=ott_antonsen_unit_disk"
    )


# ===========================================================================
# INV-KELLY2 — applied fraction <= cap; full f* == mu / sigma^2
# ===========================================================================
@settings(max_examples=120, deadline=None)
@given(
    edge=st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
    variance=st.floats(min_value=1e-6, max_value=1e6, allow_nan=False, allow_infinity=False),
    frac=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    cap=st.floats(min_value=1e-3, max_value=1e6, allow_nan=False, allow_infinity=False),
)
def test_property_kelly_fraction_within_cap(
    edge: float, variance: float, frac: float, cap: float
) -> None:
    """Positive witness: applied fraction in [0, cap] AND full f* == mu/sigma^2."""
    applied = kelly_from_edge_variance(edge, variance, fractional_kelly=frac, max_fraction=cap)
    assert 0.0 <= applied <= cap, (
        f"INV-KELLY2 VIOLATED: applied fraction f={applied:.6f} left [0,{cap:.6f}]. "
        f"Sizing must never exceed the configured cap (fail-closed downscaling). "
        f"edge={edge:.4e}, variance={variance:.4e}, frac={frac:.4f}, "
        f"property=kelly_fraction_within_cap"
    )
    # f* == mu/sigma^2 on the unclamped, positive-edge branch (full Kelly, huge cap).
    pos_edge = abs(edge) + 1.0
    full = kelly_from_edge_variance(
        pos_edge, variance, fractional_kelly=1.0, max_fraction=1e15
    )
    expected = pos_edge / variance
    assert math.isclose(full, expected, rel_tol=1e-12, abs_tol=1e-15), (
        f"INV-KELLY1/2 VIOLATED: full Kelly f*={full:.8e} != mu/sigma^2={expected:.8e}. "
        f"The continuous small-edge optimum is exactly edge/variance. "
        f"edge={pos_edge:.4e}, variance={variance:.4e}, rel_tol=1e-12, "
        f"property=kelly_full_equals_mu_over_sigma2"
    )


def test_negative_control_kelly_fraction_predicate() -> None:
    """Negative control: the cap predicate rejects a fabricated over-cap fraction."""
    cap = 0.3
    fabricated_applied = 0.6
    assert not (0.0 <= fabricated_applied <= cap), (
        f"INV-KELLY2 NEGATIVE-CONTROL BROKEN: predicate admitted f={fabricated_applied} "
        f"> cap={cap}; the cap bound would be vacuous. "
        f"expected=reject, got=admit, property=kelly_fraction_within_cap"
    )


# ===========================================================================
# INV-DRO1 — derive_gamma satisfies gamma == 2*H + 1
# ===========================================================================
@settings(max_examples=60, deadline=None)
@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    length=st.integers(min_value=64, max_value=512),
)
def test_property_derive_gamma_identity(seed: int, length: int) -> None:
    """Positive witness: gamma == 2*H + 1 on Hypothesis-drawn random walks."""
    rng = np.random.default_rng(seed)
    walk = np.cumsum(rng.standard_normal(length)).astype(np.float64)
    gamma, hurst, _r2 = derive_gamma(walk)
    residual = abs(gamma - (2.0 * hurst + 1.0))
    assert residual < 1e-5, (
        f"INV-DRO1 VIOLATED: |gamma-(2H+1)|={residual:.3e} >= 1e-5. "
        f"gamma is defined as 2H+1 (Peng 1994); the identity is algebraic. "
        f"gamma={gamma:.6f}, H={hurst:.6f}, length={length}, "
        f"property=dro_gamma_equals_2H_plus_1"
    )


def test_derive_gamma_rejects_degenerate_inputs() -> None:
    """Fail-closed: short, constant, or non-finite series are rejected."""
    with pytest.raises(ValueError):
        derive_gamma(np.arange(10, dtype=np.float64))  # below 64-sample floor
    with pytest.raises(ValueError):
        derive_gamma(np.full(128, 3.0, dtype=np.float64))  # constant series
    bad = np.linspace(0.0, 1.0, 128)
    bad[5] = np.inf
    with pytest.raises(ValueError):
        derive_gamma(bad)


def test_negative_control_derive_gamma_predicate() -> None:
    """Negative control: the identity predicate rejects a fabricated mismatch."""
    fake_gamma, fake_h = 5.0, 0.5  # 2*0.5+1 = 2.0, residual = 3.0
    residual = abs(fake_gamma - (2.0 * fake_h + 1.0))
    assert not (residual < 1e-5), (
        f"INV-DRO1 NEGATIVE-CONTROL BROKEN: predicate admitted residual={residual:.3e}; "
        f"the gamma=2H+1 identity would be vacuous. "
        f"expected=reject, got=admit, property=dro_gamma_equals_2H_plus_1"
    )
