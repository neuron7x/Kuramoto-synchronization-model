# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cross-feature integration test for the four research extensions.

Composes - without mocking - a deterministic pipeline that exercises:

1. Capital-weighted beta-Kuramoto coupling
   (``core.kuramoto.capital_weighted``)
2. Discrete Ricci flow + neckpinch surgery
   (``core.kuramoto.ricci_flow``)
3. Sparse simplicial higher-order Kuramoto
   (``core.physics.higher_order_kuramoto`` - sparse path)
4. DR-FREE distributionally robust free-energy gating
   (``tacl.dr_free``)

The test enforces the GeoSync physics contract:

- INV-K1 (universal):   R(t) in [0, 1] every step.
- INV-HPC1 (universal): bit-identical replay under fixed seed.
- INV-HPC2 (universal): finite inputs imply finite outputs.
- INV-RC-FLOW (module): post-flow weights finite, symmetric, non-negative,
  zero-diagonal.
- INV-FE-ROBUST (module): F_robust >= F_nominal for every box radius
  >= 0, equality at zero radius, monotone in radius.

No look-ahead is permitted: ``snapshot.timestamp_ns <= signal_timestamp_ns``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import pytest
from numpy.typing import NDArray

from core.kuramoto.capital_weighted import (
    CapitalWeightedCouplingConfig,
    CapitalWeightedCouplingResult,
    L2DepthSnapshot,
    build_capital_weighted_adjacency,
)
from core.kuramoto.ricci_flow import (
    RicciFlowConfig,
    RicciFlowStepResult,
    ricci_flow_with_surgery,
)
from core.physics.higher_order_kuramoto import (
    HigherOrderKuramotoResult,
    HigherOrderSparseConfig,
    SparseTriangleIndex,
    build_sparse_triangle_index,
    run_sparse_higher_order,
)
from tacl.dr_free import AmbiguitySet, DRFreeEnergyModel, robust_energy_state
from tacl.energy_model import EnergyMetrics

# -- Determinism contract -------------------------------------------------
_SEED: Final[int] = 20260425
_N_NODES: Final[int] = 16
_N_LEVELS: Final[int] = 5
_KURAMOTO_STEPS: Final[int] = 50
_DT: Final[float] = 0.02

# Snapshot timestamps must be <= signal timestamp; violating this is leakage.
_SIGNAL_TS_NS: Final[int] = 1_700_000_000_000_000_000  # 2023-11-14T22:13:20Z, ns
_L2_TS_NS: Final[int] = _SIGNAL_TS_NS - 1_000_000_000  # one second earlier


# -- Typed bundle so mypy --strict can see every attribute access ---------


@dataclass(frozen=True)
class PipelineOutput:
    """Typed bundle carrying every intermediate pipeline artefact."""

    cw_result: CapitalWeightedCouplingResult
    K: NDArray[np.float64]
    rf_result: RicciFlowStepResult
    W_post: NDArray[np.float64]
    adj_bool: NDArray[np.bool_]
    triangle_index: SparseTriangleIndex
    ho_result: HigherOrderKuramotoResult
    metrics: EnergyMetrics
    dr_model: DRFreeEnergyModel
    nominal_free_energy: float


# -- Fixtures: deterministic synthetic L2 + baseline graph ----------------


def _make_l2_snapshot(rng: np.random.Generator) -> L2DepthSnapshot:
    """Synthetic L2 with non-uniform depth so beta meaningfully reshapes coupling."""
    bid = rng.uniform(low=1.0, high=50.0, size=(_N_NODES, _N_LEVELS))
    ask = rng.uniform(low=1.0, high=50.0, size=(_N_NODES, _N_LEVELS))
    mid = rng.uniform(low=10.0, high=200.0, size=_N_NODES)
    # Skew the first three nodes so depth-mass distribution is non-uniform.
    bid[:3] *= 8.0
    ask[:3] *= 8.0
    return L2DepthSnapshot(
        timestamp_ns=_L2_TS_NS,
        bid_sizes=bid.astype(np.float64),
        ask_sizes=ask.astype(np.float64),
        mid_prices=mid.astype(np.float64),
    )


def _make_baseline_adjacency(rng: np.random.Generator) -> NDArray[np.float64]:
    """Symmetric, non-negative, zero-diagonal baseline coupling."""
    raw = rng.uniform(low=0.0, high=1.0, size=(_N_NODES, _N_NODES))
    raw = 0.5 * (raw + raw.T)
    np.fill_diagonal(raw, 0.0)
    return raw.astype(np.float64)


def _forman_curvature(weights: NDArray[np.float64]) -> dict[tuple[int, int], float]:
    """Forman-style edge curvature on a weighted graph.

    Combinatorial Forman with unit vertex weights:
        F(e) = 2 - sum_{e' ~ e, e' != e} sqrt(w_e / w_{e'})
    The output is bounded (no NaN/Inf) and matches the
    ``Mapping[tuple[int,int], float]`` interface
    ``ricci_flow_with_surgery`` expects.
    """
    n = int(weights.shape[0])
    curv: dict[tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            w_e = float(weights[i, j])
            if w_e <= 0.0:
                continue
            neigh_sum = 0.0
            for v in (i, j):
                for k in range(n):
                    if k in (i, j):
                        continue
                    w_n = float(weights[v, k])
                    if w_n <= 0.0:
                        continue
                    neigh_sum += math.sqrt(w_e / w_n)
            kappa = 2.0 - neigh_sum
            # bounds: keep curvature finite for the Ricci flow step;
            # the module accepts any finite curvature.
            curv[(i, j)] = float(np.clip(kappa, -1.0e3, 1.0e3))
    return curv


# -- Pipeline -------------------------------------------------------------


def _run_pipeline(
    *,
    seed: int = _SEED,
    binarize_threshold: float | None = None,
    corrupt_l2: bool = False,
    snapshot_override: L2DepthSnapshot | None = None,
) -> PipelineOutput:
    """Execute the full four-feature pipeline.

    Parameters
    ----------
    seed:
        Seed for the deterministic RNG.
    binarize_threshold:
        Edge-presence threshold (relative to max post-flow weight).
        If ``None``, defaults to the median non-zero weight.
    corrupt_l2:
        If True, inject a NaN into ``bid_sizes`` to assert fail-closed.
    snapshot_override:
        Optional pre-built snapshot.
    """
    rng = np.random.default_rng(seed)
    baseline_adj = _make_baseline_adjacency(rng)
    snapshot = snapshot_override if snapshot_override is not None else _make_l2_snapshot(rng)

    if corrupt_l2:
        bid = snapshot.bid_sizes.copy()
        bid[0, 0] = float("nan")
        snapshot = L2DepthSnapshot(
            timestamp_ns=snapshot.timestamp_ns,
            bid_sizes=bid,
            ask_sizes=snapshot.ask_sizes,
            mid_prices=snapshot.mid_prices,
        )

    # -- Feature 1: capital-weighted beta coupling ---------------------
    cw_cfg = CapitalWeightedCouplingConfig(
        K0=1.0, gamma=1.0, delta=1.0, beta_min=0.25, beta_max=4.0
    )
    cw_result = build_capital_weighted_adjacency(
        baseline_adj=baseline_adj,
        snapshot=snapshot,
        signal_timestamp_ns=_SIGNAL_TS_NS,
        cfg=cw_cfg,
    )
    K: NDArray[np.float64] = cw_result.coupling

    # -- Feature 2: discrete Ricci flow + neckpinch surgery ------------
    curvature = _forman_curvature(K)
    rf_cfg = RicciFlowConfig(
        eta=0.05,
        eps_weight=1e-6,
        eps_neck=1e-3,
        preserve_total_edge_mass=True,
        preserve_connectedness=True,
        max_surgery_fraction=0.05,
    )
    rf_result = ricci_flow_with_surgery(K, curvature, rf_cfg)
    W_post: NDArray[np.float64] = rf_result.weights_after

    # -- Feature 3: sparse simplicial triangle index -------------------
    if binarize_threshold is None:
        nonzero = W_post[W_post > 0.0]
        binarize_threshold = float(np.median(nonzero)) if nonzero.size > 0 else 0.0
    adj_bool: NDArray[np.bool_] = (W_post > binarize_threshold).astype(bool)
    np.fill_diagonal(adj_bool, False)
    # Enforce exact symmetry (binarisation can introduce 1-bit asymmetry).
    adj_bool = adj_bool & adj_bool.T

    triangle_index = build_sparse_triangle_index(adj_bool, max_triangles=10_000)

    # Initial phases / frequencies - derived from the seeded RNG so the
    # whole pipeline is replayable.
    omega: NDArray[np.float64] = rng.standard_normal(_N_NODES).astype(np.float64)
    theta0: NDArray[np.float64] = rng.uniform(low=0.0, high=2.0 * np.pi, size=_N_NODES).astype(
        np.float64
    )

    sparse_cfg = HigherOrderSparseConfig(sigma1=1.0, sigma2=0.4, max_triangles=10_000)
    ho_result = run_sparse_higher_order(
        adj=adj_bool,
        omega=omega,
        theta0=theta0,
        cfg=sparse_cfg,
        dt=_DT,
        steps=_KURAMOTO_STEPS,
    )

    # -- Feature 4: DR-FREE evaluation on derived EnergyMetrics --------
    R_final = float(ho_result.order_parameter[-1])
    R_mean = float(ho_result.order_parameter.mean())
    triadic_max = float(ho_result.triadic_contribution.max())
    metrics = EnergyMetrics(
        latency_p95=60.0 + 30.0 * (1.0 - R_mean),
        latency_p99=90.0 + 40.0 * (1.0 - R_mean),
        coherency_drift=float(np.clip(0.05 + 0.05 * (1.0 - R_final), 0.0, 1.0)),
        cpu_burn=float(np.clip(0.4 + 0.2 * triadic_max / max(1.0, omega.std()), 0.0, 1.0)),
        mem_cost=4.0,
        queue_depth=20.0,
        packet_loss=0.002,
    )

    dr = DRFreeEnergyModel()
    nominal_F, _, _, _ = dr.base_model.free_energy(metrics)

    return PipelineOutput(
        cw_result=cw_result,
        K=K,
        rf_result=rf_result,
        W_post=W_post,
        adj_bool=adj_bool,
        triangle_index=triangle_index,
        ho_result=ho_result,
        metrics=metrics,
        dr_model=dr,
        nominal_free_energy=float(nominal_F),
    )


# -- Tests ----------------------------------------------------------------


def test_full_pipeline_executes_without_error() -> None:
    """Pipeline must run end-to-end and emit per-feature invariants."""
    out = _run_pipeline()
    cw = out.cw_result
    K = out.K
    rf = out.rf_result
    W_post = out.W_post
    ho = out.ho_result
    R = ho.order_parameter

    # Feature 1 - INV-KBETA: K finite, symmetric, zero-diagonal.
    assert np.isfinite(K).all(), "INV-HPC2 VIOLATED: K contains non-finite values."
    assert np.allclose(K, K.T, atol=1e-10), "INV-KBETA VIOLATED: K must be symmetric."
    assert np.allclose(np.diag(K), 0.0, atol=1e-12), "INV-KBETA VIOLATED: K diagonal must be zero."
    assert (K >= -1e-12).all(), "INV-KBETA VIOLATED: K must be non-negative."
    assert 0.25 <= cw.beta <= 4.0, f"beta={cw.beta} outside [beta_min, beta_max]."

    # Feature 2 - INV-RC-FLOW: post-flow finite, symmetric, non-negative.
    assert np.isfinite(W_post).all(), "INV-RC-FLOW VIOLATED: post-flow weights non-finite."
    sym_w = bool(np.allclose(W_post, W_post.T, atol=1e-10))
    assert sym_w, "INV-RC-FLOW VIOLATED: post-flow weights asymmetric."
    assert (W_post >= -1e-12).all(), "INV-RC-FLOW VIOLATED: post-flow weights negative."
    diag_zero = bool(np.allclose(np.diag(W_post), 0.0, atol=1e-12))
    assert diag_zero, "INV-RC-FLOW VIOLATED: post-flow weights have non-zero diagonal."
    # Surgery events recorded (may be zero, but the field must exist).
    assert rf.surgery_event_count >= 0

    # Feature 3 - INV-K1 + INV-HPC2: R bounded, all phases finite.
    assert np.isfinite(R).all(), "INV-HPC2 VIOLATED: R(t) contains non-finite values."
    r_bounded = bool(((R >= 0.0) & (R <= 1.0 + 1e-12)).all())
    msg_r = f"INV-K1 VIOLATED: R in [0,1] required, got [{R.min():.6f}, {R.max():.6f}]."
    assert r_bounded, msg_r
    assert np.isfinite(ho.phases).all(), "INV-HPC2 VIOLATED: phase array non-finite."

    # Feature 4 - INV-FE-ROBUST: zero-radius DR-FREE equals nominal.
    dr = out.dr_model
    metrics = out.metrics
    zero_amb = AmbiguitySet(radii={})
    zero_result = dr.evaluate_robust(metrics, zero_amb)
    delta_zero = abs(zero_result.robust_free_energy - zero_result.nominal_free_energy)
    assert delta_zero < 1e-12, "INV-FE-ROBUST VIOLATED: zero-radius robust must equal nominal."


def test_pipeline_is_deterministic_under_fixed_seed() -> None:
    """INV-HPC1: bit-identical R(t) trajectory across two runs with same seed."""
    out_a = _run_pipeline(seed=_SEED)
    out_b = _run_pipeline(seed=_SEED)
    R_a: NDArray[np.float64] = out_a.ho_result.order_parameter
    R_b: NDArray[np.float64] = out_b.ho_result.order_parameter

    np.testing.assert_array_equal(
        R_a,
        R_b,
        err_msg=(
            "INV-HPC1 VIOLATED: R(t) trajectory diverged between runs at seed "
            f"{_SEED}; first divergence at index "
            f"{int(np.argmax(R_a != R_b)) if bool((R_a != R_b).any()) else -1}."
        ),
    )

    # Post-flow weights are also bit-identical.
    np.testing.assert_array_equal(
        out_a.W_post,
        out_b.W_post,
        err_msg="INV-HPC1 VIOLATED: Ricci-flow output diverged between runs.",
    )


def test_pipeline_invariants_compose() -> None:
    """Composite check: every per-feature P0 invariant holds simultaneously."""
    out = _run_pipeline()
    K = out.K
    W_post = out.W_post
    ho = out.ho_result
    triangle_index = out.triangle_index
    R = ho.order_parameter

    # Composite assert 1: capital-weighted output is a valid baseline for
    # the Ricci flow (i.e. shape contracts compose).
    assert K.shape == W_post.shape == (_N_NODES, _N_NODES)

    # Composite assert 2: triangle index respects 0 <= i < j < k < N.
    if triangle_index.n_triangles > 0:
        assert (triangle_index.i >= 0).all()
        assert (triangle_index.k < _N_NODES).all()
        assert (triangle_index.i < triangle_index.j).all()
        assert (triangle_index.j < triangle_index.k).all()

    # Composite assert 3: R(t) bounded AND finite AND no negative dt drift.
    r_ok = bool(np.isfinite(R).all() and ((R >= 0.0) & (R <= 1.0 + 1e-12)).all())
    assert r_ok, "INV-K1/INV-HPC2 VIOLATED in composite pipeline."

    # Composite assert 4: triadic contribution magnitude finite for all steps.
    triadic = ho.triadic_contribution
    assert np.isfinite(triadic).all(), "INV-HPC2 VIOLATED: triadic magnitude non-finite."
    assert (triadic >= 0.0).all(), "triadic magnitude must be non-negative (||v||_2 >= 0)."

    # Composite assert 5: DR-FREE monotonicity holds on the pipeline output.
    dr = out.dr_model
    metrics = out.metrics
    small = AmbiguitySet(radii={"latency_p95": 0.05})
    large = AmbiguitySet(radii={"latency_p95": 0.50})
    F_small = dr.evaluate_robust(metrics, small).robust_free_energy
    F_large = dr.evaluate_robust(metrics, large).robust_free_energy
    assert F_small <= F_large + 1e-12, "INV-FE-ROBUST VIOLATED: F_robust not monotone in radius."


def test_pipeline_fails_closed_on_corrupted_l2() -> None:
    """Injecting NaN into L2 must raise - no silent fallback."""
    with pytest.raises(ValueError, match="non-finite"):
        _run_pipeline(corrupt_l2=True)


def test_pipeline_handles_no_triangles() -> None:
    """Threshold above max post-flow weight implies empty triangle index;
    sparse triadic term is identically zero, dynamics reduce to pairwise."""
    out = _run_pipeline(binarize_threshold=1.0e9)
    ti = out.triangle_index
    assert ti.n_triangles == 0, f"expected empty triangle index, got {ti.n_triangles}."

    ho = out.ho_result
    triadic = ho.triadic_contribution

    # Triadic contribution magnitude is identically zero throughout the run.
    triadic_zero = bool(np.allclose(triadic, 0.0, atol=1e-15))
    msg_tri = (
        f"expected exactly-zero triadic term in no-triangle regime, got max={triadic.max():.3e}"
    )
    assert triadic_zero, msg_tri

    # R(t) still bounded (INV-K1) and finite (INV-HPC2).
    R = ho.order_parameter
    r_ok = bool(np.isfinite(R).all() and ((R >= 0.0) & (R <= 1.0 + 1e-12)).all())
    msg_r = f"INV-K1 VIOLATED in no-triangle regime: [{R.min():.6f}, {R.max():.6f}]."
    assert r_ok, msg_r


def test_pipeline_dr_free_dormant_under_high_radius() -> None:
    """Large enough box radius drives robust state to WARNING or DORMANT."""
    out = _run_pipeline()
    dr = out.dr_model
    metrics = out.metrics
    nominal_F = out.nominal_free_energy

    warning_threshold = float(nominal_F) + 0.001
    crisis_threshold = float(nominal_F) + 1.0

    huge = AmbiguitySet(
        radii={
            "latency_p95": 5.0,
            "latency_p99": 5.0,
            "coherency_drift": 5.0,
            "cpu_burn": 5.0,
            "mem_cost": 5.0,
            "queue_depth": 5.0,
            "packet_loss": 5.0,
        }
    )
    result = dr.evaluate_robust(metrics, huge)
    state = robust_energy_state(
        result,
        warning_threshold=warning_threshold,
        crisis_threshold=crisis_threshold,
    )
    state_ok = state in {"WARNING", "DORMANT"}
    msg_state = (
        f"expected WARNING/DORMANT under huge radius, got {state} "
        f"with robust_F={result.robust_free_energy:.4f}, "
        f"nominal_F={result.nominal_free_energy:.4f}."
    )
    assert state_ok, msg_state

    # And INV-FE-ROBUST holds with strict positivity at huge radius.
    strict_inflate = result.robust_free_energy > result.nominal_free_energy
    assert strict_inflate, "INV-FE-ROBUST VIOLATED: huge radius should strictly inflate robust F."


def test_pipeline_beta_unity_recovers_baseline() -> None:
    """beta=1 path: no-L2 fallback returns the baseline unchanged with beta=1."""
    rng = np.random.default_rng(_SEED)
    baseline_adj = _make_baseline_adjacency(rng)
    cfg = CapitalWeightedCouplingConfig()
    result = build_capital_weighted_adjacency(
        baseline_adj=baseline_adj,
        snapshot=None,
        signal_timestamp_ns=_SIGNAL_TS_NS,
        cfg=cfg,
    )
    assert result.used_fallback is True
    assert result.beta == pytest.approx(1.0, abs=1e-15)
    np.testing.assert_array_equal(result.coupling, baseline_adj)


def test_pipeline_rejects_future_l2_snapshot() -> None:
    """Look-ahead leakage: snapshot.timestamp_ns > signal_timestamp_ns is fatal."""
    rng = np.random.default_rng(_SEED)
    baseline_adj = _make_baseline_adjacency(rng)
    snapshot = _make_l2_snapshot(rng)
    future = L2DepthSnapshot(
        timestamp_ns=_SIGNAL_TS_NS + 1,
        bid_sizes=snapshot.bid_sizes,
        ask_sizes=snapshot.ask_sizes,
        mid_prices=snapshot.mid_prices,
    )
    cfg = CapitalWeightedCouplingConfig(fail_on_future_l2=True)
    with pytest.raises(ValueError, match="look-ahead"):
        build_capital_weighted_adjacency(
            baseline_adj=baseline_adj,
            snapshot=future,
            signal_timestamp_ns=_SIGNAL_TS_NS,
            cfg=cfg,
        )
