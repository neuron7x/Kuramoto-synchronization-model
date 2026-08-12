# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Metamorphic falsification witnesses for the executable physics-contract layer.

A metamorphic relation constrains how a solver's output must change (or stay
fixed) under a *transformation of its input*. These properties catch a class of
bugs that point-tests miss: a solver can return a plausible value for every
individual input yet still violate the symmetry that connects related inputs
(e.g. a rotation that silently shifts an order parameter, or a cost that is not
linear in temperature). Each relation below is evaluated on the REAL solver; the
positive witness proves the relation holds across several seeds/parameters, and
the negative control corrupts ONE side of the relation to prove the metamorphic
check is a live falsifier rather than a vacuous tautology.

Nothing here is a market claim. These are invariance/scaling facts about the
code under input transformations.

Headline catalog laws (physics_contracts/falsification_catalog.yaml):
- metamorphic_order_parameter_rotation_invariance
- metamorphic_landauer_temperature_linearity
"""

from __future__ import annotations

from fractions import Fraction

import networkx as nx
import numpy as np

from analytics.math_trading.kelly_criterion import kelly_from_edge_variance
from core.indicators.gauss_bonnet import euler_characteristic, knill_vertex_curvature
from core.kuramoto.ott_antonsen import OttAntonsenEngine
from core.physics.landauer import bit_erasure_cost
from core.physics.ricci_kuramoto import compute_order_parameter

# Machine-tolerance budgets. Exact relations (integers / closed-form algebra)
# get a tiny float-rounding budget; closed-form floating relations get a modest
# relative budget tied to the operation count, never a magic fudge factor.
_TOL_MACHINE = 1e-12
_TOL_FLOAT = 1e-9


def _knill_sum(graph: nx.Graph) -> Fraction:
    """Exact sum of Knill vertex curvature over ``graph`` (no float slack)."""
    return sum(knill_vertex_curvature(graph).values(), Fraction(0))


# ---------------------------------------------------------------------------
# Relation 1: Kuramoto order parameter is invariant under a global phase shift.
# R = |mean(exp(i*theta))|; adding a constant c rotates every unit vector by the
# same angle, which factors out of the modulus -> R is shift-invariant.
# ---------------------------------------------------------------------------
def test_order_parameter_rotation_invariance_holds() -> None:
    """Positive witness: R(phases) == R(phases + c) to machine tolerance."""
    rng = np.random.default_rng(20260627)
    for seed in range(8):
        n = int(rng.integers(8, 256))
        phases = rng.uniform(-np.pi, np.pi, size=n)
        for c in (0.0, 0.37, 1.0, np.pi, -2.5, 100.0):
            lhs = compute_order_parameter(phases)
            rhs = compute_order_parameter(phases + c)
            residual = abs(lhs - rhs)
            assert residual <= _TOL_MACHINE, (
                f"METAMORPHIC ROTATION-INVARIANCE VIOLATED | relation=R(theta)==R(theta+c) "
                f"| seed={seed} c={c} n={n} | R(theta)={lhs!r} R(theta+c)={rhs!r} "
                f"| residual={residual:.3e} tol={_TOL_MACHINE:.1e}"
            )


def test_order_parameter_rotation_with_amplitude_corruption_is_rejected() -> None:
    """Negative control: rotate by c but ALSO scale the amplitude -> relation breaks.

    R is invariant only under a pure phase shift. If the transformed output is
    additionally scaled by an amplitude a != 1 (|mean(a*exp(i theta))| = a*R),
    the invariance is destroyed. The metamorphic check must flag this.
    """
    rng = np.random.default_rng(11)
    flagged = 0
    total = 0
    for seed in range(8):
        phases = rng.uniform(-np.pi, np.pi, size=64)
        c = 0.9
        for amplitude in (0.5, 1.5, 2.0):
            lhs = compute_order_parameter(phases)
            corrupted_rhs = amplitude * compute_order_parameter(phases + c)
            residual = abs(lhs - corrupted_rhs)
            total += 1
            if residual > _TOL_MACHINE:
                flagged += 1
    assert flagged == total, (
        f"METAMORPHIC CHECK IS VACUOUS | relation=R(theta)==a*R(theta+c) for a!=1 "
        f"| expected ALL corrupted cases flagged | flagged={flagged} total={total} "
        f"| tol={_TOL_MACHINE:.1e}"
    )


# ---------------------------------------------------------------------------
# Relation 2: Landauer cost is linear in temperature and additive in bits.
# cost = k_B * T * ln2 * bits, so cost(1, a*T) == a*cost(1, T) and
# cost(n, T) == n*cost(1, T). Exact (single multiplication chain).
# ---------------------------------------------------------------------------
def test_landauer_temperature_linearity_holds() -> None:
    """Positive witness: cost(1, a*T) == a*cost(1, T) and cost(n,T) == n*cost(1,T)."""
    for temperature in (4.2, 77.0, 300.0, 1000.0):
        for a in (0.5, 2.0, 3.0, 10.0):
            lhs = bit_erasure_cost(1.0, a * temperature)
            rhs = a * bit_erasure_cost(1.0, temperature)
            residual = abs(lhs - rhs)
            tol = _TOL_MACHINE * abs(rhs)  # relative: costs live at the k_B (~1e-23) scale
            assert residual <= tol, (
                f"METAMORPHIC LANDAUER T-LINEARITY VIOLATED | relation=cost(1,a*T)==a*cost(1,T) "
                f"| T={temperature} a={a} | lhs={lhs!r} rhs={rhs!r} "
                f"| residual={residual:.3e} tol={tol:.1e}"
            )
        for n in (1.0, 8.0, 64.0, 1024.0):
            lhs_n = bit_erasure_cost(n, temperature)
            rhs_n = n * bit_erasure_cost(1.0, temperature)
            residual_n = abs(lhs_n - rhs_n)
            tol_n = _TOL_MACHINE * abs(rhs_n)  # relative (k_B scale)
            assert residual_n <= tol_n, (
                f"METAMORPHIC LANDAUER BIT-ADDITIVITY VIOLATED | relation=cost(n,T)==n*cost(1,T) "
                f"| T={temperature} n={n} | lhs={lhs_n!r} rhs={rhs_n!r} "
                f"| residual={residual_n:.3e} tol={tol_n:.1e}"
            )


def test_landauer_wrong_scaling_factor_is_rejected() -> None:
    """Negative control: a WRONG scaling factor (a -> a+0.5) breaks T-linearity.

    The relation pins the slope to exactly k_B*ln2*bits. If the predicted output
    uses the wrong multiplier, the metamorphic check must reject it -- proving the
    check discriminates the true slope, not just any monotone trend.
    """
    flagged = 0
    total = 0
    for temperature in (4.2, 300.0, 1000.0):
        for a in (0.5, 2.0, 3.0):
            lhs = bit_erasure_cost(1.0, a * temperature)
            wrong_factor = a + 0.5
            corrupted_rhs = wrong_factor * bit_erasure_cost(1.0, temperature)
            residual = abs(lhs - corrupted_rhs)
            tol = _TOL_MACHINE * abs(lhs)  # relative (k_B scale)
            total += 1
            if residual > tol:
                flagged += 1
    assert flagged == total, (
        f"METAMORPHIC CHECK IS VACUOUS | relation=cost(1,a*T)==(a+0.5)*cost(1,T) "
        f"| expected ALL wrong-factor cases flagged | flagged={flagged} total={total}"
    )


# ---------------------------------------------------------------------------
# Relation 3: Kelly fraction scales inversely with variance and linearly in edge.
# f* = (edge/variance)*frac (capped). For a non-binding cap:
#   kelly(mu, c*sigma2) == kelly(mu, sigma2)/c   and   kelly(a*mu, sigma2) == a*kelly(mu, sigma2).
# ---------------------------------------------------------------------------
def test_kelly_variance_and_edge_scaling_holds() -> None:
    """Positive witness: inverse-variance and linear-in-edge scaling (non-binding cap)."""
    base_edge = 0.01
    base_var = 0.04  # base kelly = (0.01/0.04)*0.5 = 0.125, far below cap 1.0
    for c in (0.5, 2.0, 4.0):
        lhs = kelly_from_edge_variance(base_edge, c * base_var)
        rhs = kelly_from_edge_variance(base_edge, base_var) / c
        residual = abs(lhs - rhs)
        assert residual <= _TOL_FLOAT, (
            f"METAMORPHIC KELLY INVERSE-VARIANCE VIOLATED | relation=k(mu,c*s2)==k(mu,s2)/c "
            f"| c={c} mu={base_edge} s2={base_var} | lhs={lhs!r} rhs={rhs!r} "
            f"| residual={residual:.3e} tol={_TOL_FLOAT:.1e}"
        )
    for a in (0.5, 2.0, 4.0):
        lhs_e = kelly_from_edge_variance(a * base_edge, base_var)
        rhs_e = a * kelly_from_edge_variance(base_edge, base_var)
        residual_e = abs(lhs_e - rhs_e)
        assert residual_e <= _TOL_FLOAT, (
            f"METAMORPHIC KELLY EDGE-LINEARITY VIOLATED | relation=k(a*mu,s2)==a*k(mu,s2) "
            f"| a={a} mu={base_edge} s2={base_var} | lhs={lhs_e!r} rhs={rhs_e!r} "
            f"| residual={residual_e:.3e} tol={_TOL_FLOAT:.1e}"
        )


def test_kelly_wrong_variance_exponent_is_rejected() -> None:
    """Negative control: dividing by c**2 (wrong exponent) breaks inverse-variance.

    Kelly scales as 1/variance, NOT 1/variance**2. A corrupted prediction using
    the wrong exponent must be flagged -- proving the check pins the exponent.
    """
    base_edge = 0.01
    base_var = 0.04
    flagged = 0
    total = 0
    for c in (2.0, 4.0):
        lhs = kelly_from_edge_variance(base_edge, c * base_var)
        corrupted_rhs = kelly_from_edge_variance(base_edge, base_var) / (c * c)
        residual = abs(lhs - corrupted_rhs)
        total += 1
        if residual > _TOL_FLOAT:
            flagged += 1
    assert flagged == total, (
        f"METAMORPHIC CHECK IS VACUOUS | relation=k(mu,c*s2)==k(mu,s2)/c**2 "
        f"| expected ALL wrong-exponent cases flagged | flagged={flagged} total={total}"
    )


# ---------------------------------------------------------------------------
# Relation 4: Gauss-Bonnet quantities are additive over a disjoint union.
# chi(G u H) == chi(G) + chi(H); sum_x K(x) is likewise additive. EXACT integers.
# ---------------------------------------------------------------------------
def test_gauss_bonnet_disjoint_union_additivity_holds() -> None:
    """Positive witness: Euler char and Knill curvature sum are additive over G u H."""
    families: list[tuple[str, nx.Graph]] = [
        ("cycle5", nx.cycle_graph(5)),
        ("complete4", nx.complete_graph(4)),
        ("path7", nx.path_graph(7)),
        ("star6", nx.star_graph(6)),
        ("tree", nx.balanced_tree(2, 3)),
    ]
    for name_g, graph_g in families:
        for name_h, graph_h in families:
            union = nx.disjoint_union(graph_g, graph_h)

            chi_lhs = euler_characteristic(union)
            chi_rhs = euler_characteristic(graph_g) + euler_characteristic(graph_h)
            assert chi_lhs == chi_rhs, (
                f"METAMORPHIC GAUSS-BONNET EULER-ADDITIVITY VIOLATED "
                f"| relation=chi(G u H)==chi(G)+chi(H) | G={name_g} H={name_h} "
                f"| chi(union)={chi_lhs} chi(G)+chi(H)={chi_rhs} residual={chi_lhs - chi_rhs}"
            )

            curv_lhs = _knill_sum(union)
            curv_rhs = _knill_sum(graph_g) + _knill_sum(graph_h)
            assert curv_lhs == curv_rhs, (
                f"METAMORPHIC KNILL-CURVATURE-ADDITIVITY VIOLATED "
                f"| relation=sum K(G u H)==sum K(G)+sum K(H) | G={name_g} H={name_h} "
                f"| sum(union)={curv_lhs} sum(G)+sum(H)={curv_rhs} "
                f"| residual={curv_lhs - curv_rhs}"
            )


def test_gauss_bonnet_cross_linked_union_breaks_additivity() -> None:
    """Negative control: a single cross-edge makes the union NOT disjoint -> additivity breaks.

    Additivity is specific to a *disjoint* union. Adding one edge between the two
    components changes the topology (merges/creates simplices), so the additive
    identity must fail -- proving the relation is a live falsifier of the
    disjointness assumption, not a tautology.
    """
    graph_g = nx.cycle_graph(5)
    graph_h = nx.complete_graph(4)
    union = nx.disjoint_union(graph_g, graph_h)
    # Connect a node of the former G-component to a node of the former H-component.
    cross_linked = union.copy()
    cross_linked.add_edge(0, graph_g.number_of_nodes())  # node 0 (G) -- node 5 (H)

    chi_joined = euler_characteristic(cross_linked)
    chi_additive = euler_characteristic(graph_g) + euler_characteristic(graph_h)
    assert chi_joined != chi_additive, (
        f"METAMORPHIC CHECK IS VACUOUS | relation should FAIL for a cross-linked (non-disjoint) "
        f"union | chi(cross_linked)={chi_joined} chi(G)+chi(H)={chi_additive} "
        f"| residual={chi_joined - chi_additive} (expected non-zero)"
    )


# ---------------------------------------------------------------------------
# Relation 5: Ott-Antonsen steady state is monotone non-decreasing in K.
# R_inf = sqrt(1 - K_c/K) for K > K_c is strictly increasing in K.
# ---------------------------------------------------------------------------
def test_ott_antonsen_steady_state_monotone_in_coupling_holds() -> None:
    """Positive witness: R_steady(K1) <= R_steady(K2) for K_c < K1 < K2."""
    for delta in (0.5, 1.0, 2.5):
        k_c = 2.0 * delta
        couplings = [k_c * f for f in (1.1, 1.5, 2.0, 4.0, 10.0)]
        engines = [OttAntonsenEngine(K=k, delta=delta) for k in couplings]
        steady = [e.R_steady for e in engines]
        for i in range(len(steady) - 1):
            assert steady[i] <= steady[i + 1] + _TOL_MACHINE, (
                f"METAMORPHIC OA MONOTONICITY VIOLATED | relation=R_steady(K) non-decreasing "
                f"| delta={delta} K1={couplings[i]} K2={couplings[i + 1]} "
                f"| R(K1)={steady[i]!r} R(K2)={steady[i + 1]!r} "
                f"| drop={steady[i] - steady[i + 1]:.3e}"
            )


def test_ott_antonsen_inverted_coupling_law_breaks_monotonicity() -> None:
    """Negative control: a corrupted steady state that DECREASES with K is non-monotone.

    The true supercritical branch increases with K. A surrogate that scales as
    K_c/K (decreasing) must be flagged as violating the monotonicity relation --
    proving the check discriminates the direction of the dependence.
    """
    delta = 1.0
    k_c = 2.0 * delta
    couplings = [k_c * f for f in (1.1, 1.5, 2.0, 4.0, 10.0)]
    engines = [OttAntonsenEngine(K=k, delta=delta) for k in couplings]
    # Corrupted "steady state": uses the real engine's K_c but the wrong (inverse) law.
    corrupted = [e.K_c / e.K for e in engines]
    violations = sum(
        1 for i in range(len(corrupted) - 1) if corrupted[i] > corrupted[i + 1] + _TOL_MACHINE
    )
    assert violations == len(corrupted) - 1, (
        f"METAMORPHIC CHECK IS VACUOUS | corrupted law K_c/K should be strictly DECREASING "
        f"| violations={violations} expected={len(corrupted) - 1} | corrupted={corrupted}"
    )
