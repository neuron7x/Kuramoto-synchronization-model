# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration-invariant witness for the Kuramoto-Ricci geometric flow engine.

Ledger
------
id: ``ricci-flow-engine`` (OPERATIONAL, ADD_TEST, P1).
Source: :mod:`core.kuramoto.ricci_flow_engine`.
Falsifier (ledger): "INV-K1 + INV-OA1 hold throughout; ricci_update producing
κ>1 ⇒ violation."

Mechanism
---------
The engine integrates the coupled system

    dθ_i/dt = ω_i + Σ_j K_ij(t)·sin(θ_j − θ_i),
    K_ij(t) = K_base · φ(κ_ij(t)),   φ(κ) = σ·(1 + tanh(ακ))/2,

where the edge curvature κ_ij is recomputed periodically from a rolling
correlation graph of the oscillator trajectories. Between recomputations the
coupling matrix is held constant. An opt-in discrete Ricci flow + surgery step
(:func:`core.kuramoto.ricci_flow.discrete_ricci_flow_step`) evolves the edge
weights on the *closed* coupling graph.

Invariants under witness
------------------------
- **INV-K1** — Kuramoto order parameter R = |⟨e^{iθ}⟩| ∈ [0, 1] by
  Cauchy–Schwarz; must hold at every emitted step of the flow.
- **INV-OA1** — Ott–Antonsen disk bound: the mean-field reduction lives on
  |z| ≤ 1. The finite-N empirical mean field z = ⟨e^{iθ}⟩ has |z| = R, so the
  disk bound here is the same statement as INV-K1 applied to the complex mean
  field. (This engine integrates the full finite-N ODE, not the OA closed-form
  z-equation, so the disk bound is asserted on the empirical z, which is the
  only OA observable the engine produces.)
- **INV-RC1** — Ollivier–Ricci κ ≤ 1 universal upper bound. The lazy-random-walk
  Ollivier curvature is κ_xy = 1 − W₁(μ_x, μ_y)/d_xy with W₁ ≥ 0 and d_xy > 0,
  so κ ≤ 1 always; equality only when the transport cost vanishes.
- **Flow energy / total-edge-mass monotonicity** — on the *declared closed-graph
  domain* (square, symmetric, non-negative, zero-diagonal weight matrix) the
  mass-preserving discrete flow conserves Σ w_ij exactly (the discrete flow's
  conserved "energy"); the flow-energy descent is therefore the trivial
  monotone equality F_after = F_before.
- **Domain refusal (key falsifier)** — an *open / non-closed* topology
  (asymmetric, self-looped, negative, or non-finite weight matrix) is REFUSED
  with :class:`ValueError`, never silently coerced.

Validity domain
---------------
Closed, finite, attractive coupling graph: square symmetric non-negative
zero-diagonal weight matrix; finite ω, θ₀; K_base ≥ 0, σ > 0. Outside this
domain the engine fails closed (raises), which is exactly what the refusal
witnesses below assert.

Tolerances (all formula-derived; no magic numbers)
--------------------------------------------------
- ``_R_EPS`` — INV-K1/INV-OA1 round-off envelope for the order parameter. R is
  computed as |mean(exp(iθ))| over N unit complex numbers; the magnitude has
  relative error ~N·eps. With N ≤ 64 and eps = 2.22e-16 this is ≤ 1.4e-14, so a
  bound of 1e-8 is many orders above the round-off floor while still far below
  any dynamical excursion (the engine itself fails closed at R > 1 + 1e-8 in
  :func:`core.kuramoto.engine._order_parameter`). We assert the strict math
  bound R ∈ [0, 1] with this round-off slack only.
- ``_KAPPA_EPS`` — INV-RC1 round-off envelope. κ = 1 − TV is a single
  subtraction of two O(1) sums, so the absolute round-off is a few ulps ~ 1e-15;
  1e-9 is a conservative ceiling derived from float64 eps and far below 1.
- ``_MASS_RTOL`` — relative tolerance for total-edge-mass conservation. The
  mass-preserving step rescales by total_before/total_after, a single division
  and an n²-term sum reduction; the accumulated relative error is ≤ n²·eps. For
  n ≤ 8 that is ≤ 64·2.22e-16 ≈ 1.4e-14, so an rtol of 1e-12 is a safe ceiling.

NON-CLAIM
---------
Synthetic-only. This is a *geometric observer* test: it witnesses mathematical
invariants of the coupled flow on synthetic oscillators. It is **not** a
market-causality or price-graph claim unless the supplied topology is the
declared price graph.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.ricci_flow import RicciFlowConfig, discrete_ricci_flow_step
from core.kuramoto.ricci_flow_engine import (
    KuramotoRicciFlowEngine,
    KuramotoRicciFlowResult,
    _LocalOllivierRicciCurvatureLite,
    _SimpleUndirectedGraph,
)

# ── Formula-derived tolerances (see module docstring for derivations) ────────
_FLOAT_EPS: float = float(np.finfo(np.float64).eps)  # 2.220446049250313e-16
# INV-K1 / INV-OA1: |mean of N unit phasors| has rel error ~ N·eps ≤ 1.4e-14 for
# N ≤ 64; 1e-8 matches the engine's own round-off envelope and stays << any
# dynamical excursion.
_R_EPS: float = 1e-8
# INV-RC1: κ = 1 − TV is one subtraction; round-off is a few ulps (~1e-15).
_KAPPA_EPS: float = 1e-9
# Mass conservation: ≤ n²·eps ≈ 1.4e-14 for n ≤ 8; 1e-12 is a safe ceiling.
_MASS_RTOL: float = 1e-12


def _build_engine(
    *,
    n: int = 8,
    steps: int = 240,
    k: float = 1.5,
    seed: int = 7,
    enable_discrete_flow: bool = False,
) -> KuramotoRicciFlowEngine:
    """Construct an engine on the declared closed-graph domain."""
    cfg = KuramotoConfig(N=n, K=k, steps=steps, dt=0.01, seed=seed)
    return KuramotoRicciFlowEngine(
        cfg,
        ricci_update_interval=20,
        correlation_window=32,
        enable_discrete_flow=enable_discrete_flow,
    )


@pytest.fixture(scope="module")
def flow_result() -> KuramotoRicciFlowResult:
    """One deterministic flow run reused by the read-only invariant witnesses."""
    return _build_engine().run()


# ── INV-K1: Kuramoto order parameter R ∈ [0, 1] through the flow ──────────────


def test_inv_k1_order_parameter_in_unit_interval(
    flow_result: KuramotoRicciFlowResult,
) -> None:
    """R(t) ∈ [0, 1] at every emitted step (Cauchy–Schwarz, INV-K1)."""
    r = flow_result.order_parameter
    assert r.shape[0] == flow_result.config.steps + 1
    assert np.isfinite(r).all()
    assert float(r.min()) >= -_R_EPS
    assert float(r.max()) <= 1.0 + _R_EPS


def test_inv_k1_failclosed_on_divergence() -> None:
    """The flow raises (never coerces) if the order parameter leaves [0, 1].

    Witnesses the engine's in-loop INV-K1 guard: a NaN injected into ``_omega``
    drives a non-finite phase, which the engine rejects with FloatingPointError
    rather than emitting an out-of-range R.
    """
    eng = _build_engine(steps=50)
    eng._omega = np.full_like(eng._omega, np.nan)
    with pytest.raises((FloatingPointError, ValueError)):
        eng.run()


# ── INV-OA1: Ott–Antonsen disk bound |z| ≤ 1 on the empirical mean field ─────


def test_inv_oa1_meanfield_disk_bound(
    flow_result: KuramotoRicciFlowResult,
) -> None:
    """The empirical OA mean field z = ⟨e^{iθ}⟩ obeys |z| ≤ 1 throughout.

    |z| equals the order parameter R, so this is the OA-disk statement of the
    same Cauchy–Schwarz bound, recomputed independently from the raw phases to
    cross-check the engine's emitted R (not merely re-read it).
    """
    phases = flow_result.phases
    z = np.mean(np.exp(1j * phases), axis=1)
    z_abs = np.abs(z)
    assert np.isfinite(z_abs).all()
    assert float(z_abs.max()) <= 1.0 + _R_EPS
    # Independent recomputation must agree with the engine's stored R.
    np.testing.assert_allclose(
        z_abs, flow_result.order_parameter, atol=_R_EPS, rtol=0.0
    )


# ── INV-RC1: Ollivier–Ricci κ ≤ 1 universal upper bound ──────────────────────


def test_inv_rc1_curvature_history_upper_bound(
    flow_result: KuramotoRicciFlowResult,
) -> None:
    """Every recomputed edge curvature satisfies κ ≤ 1 (INV-RC1)."""
    curv = flow_result.curvature_history
    finite = curv[np.isfinite(curv)]
    # There must be at least one curvature update over the run.
    assert finite.size > 0
    assert float(finite.max()) <= 1.0 + _KAPPA_EPS


def test_inv_rc1_lite_estimator_never_exceeds_one() -> None:
    """The lazy-RW Ollivier estimator obeys κ = 1 − W₁/d ≤ 1 for any graph.

    Direct unit witness on the fallback estimator the engine relies on: since
    the total-variation W₁ proxy is ≥ 0 and the edge distance d_xy = 1, the
    curvature can never exceed 1.
    """
    graph = _SimpleUndirectedGraph(6)
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (0, 5), (0, 2), (1, 4)]
    for i, j in edges:
        graph.add_edge(i, j, weight=1.0)
    estimator = _LocalOllivierRicciCurvatureLite(alpha=0.5)
    for edge in edges:
        kappa = estimator.compute_edge_curvature(graph, edge)
        assert kappa <= 1.0 + _KAPPA_EPS, f"INV-RC1 violated on {edge}: κ={kappa}"


# ── Flow energy: total-edge-mass conservation on the closed-graph domain ─────


def test_flow_energy_mass_conserved_on_closed_graph() -> None:
    """Mass-preserving discrete flow conserves Σ w_ij (closed-graph energy).

    On the declared closed-graph domain the discrete Ricci flow's "energy"
    F = Σ_{i<j} w_ij is conserved exactly by the mass-preserving step, so the
    monotone descent reduces to the equality F_after = F_before.
    """
    weights = np.array(
        [
            [0.0, 1.0, 2.0, 0.5],
            [1.0, 0.0, 3.0, 1.5],
            [2.0, 3.0, 0.0, 0.7],
            [0.5, 1.5, 0.7, 0.0],
        ],
        dtype=np.float64,
    )
    curvature = {(0, 1): 0.5, (0, 2): -0.3, (1, 2): 0.9, (0, 3): 0.2, (1, 3): -0.1, (2, 3): 0.4}
    cfg = RicciFlowConfig(preserve_total_edge_mass=True)
    evolved = discrete_ricci_flow_step(weights, curvature, cfg)
    mass_before = float(weights.sum())
    mass_after = float(evolved.sum())
    np.testing.assert_allclose(mass_after, mass_before, rtol=_MASS_RTOL, atol=0.0)
    # Closed-graph structural invariants must survive the step.
    np.testing.assert_allclose(evolved, evolved.T, atol=_FLOAT_EPS * weights.size)
    np.testing.assert_allclose(np.diag(evolved), 0.0, atol=_FLOAT_EPS)
    assert (evolved >= 0.0).all()


# ── Domain refusal: open / non-closed topology is REFUSED, not coerced ───────


@pytest.mark.parametrize(
    ("name", "bad_weights"),
    [
        (
            "asymmetric_open_graph",
            np.array([[0.0, 1.0, 2.0], [0.5, 0.0, 3.0], [2.0, 3.0, 0.0]], dtype=np.float64),
        ),
        (
            "self_loop_diagonal",
            np.array([[0.4, 1.0, 2.0], [1.0, 0.0, 3.0], [2.0, 3.0, 0.0]], dtype=np.float64),
        ),
        (
            "negative_weight",
            np.array([[0.0, -1.0, 2.0], [-1.0, 0.0, 3.0], [2.0, 3.0, 0.0]], dtype=np.float64),
        ),
        (
            "non_finite_weight",
            np.array([[0.0, np.inf, 2.0], [np.inf, 0.0, 3.0], [2.0, 3.0, 0.0]], dtype=np.float64),
        ),
    ],
)
def test_open_topology_refused(name: str, bad_weights: np.ndarray) -> None:
    """Out-of-domain (open / non-closed) topology raises — the key falsifier.

    Each case violates one closed-graph axiom (symmetry, zero diagonal,
    non-negativity, finiteness). The flow must fail closed with ValueError
    rather than silently coerce the matrix into the admissible set.
    """
    curvature = {(0, 1): 0.5, (0, 2): -0.3, (1, 2): 0.9}
    cfg = RicciFlowConfig(preserve_total_edge_mass=True)
    with pytest.raises(ValueError):
        discrete_ricci_flow_step(bad_weights, curvature, cfg)


def test_engine_rejects_repulsive_coupling_claim() -> None:
    """A repulsive global K cannot claim attractive Kuramoto physics (fail-closed).

    Out-of-domain at the *configuration* boundary: negative K under the default
    attractive claim boundary is refused at config construction, so no flow on a
    repulsive graph is ever silently run.
    """
    with pytest.raises(ValueError):
        KuramotoConfig(N=6, K=-1.0, steps=10, dt=0.01, seed=1)
