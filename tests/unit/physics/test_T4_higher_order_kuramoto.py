# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T4 — Higher-order Kuramoto with triadic interaction tests."""

import numpy as np
import pytest

from core.physics.higher_order_kuramoto import (
    HigherOrderKuramotoEngine,
    HigherOrderKuramotoResult,
    build_triangle_index,
    find_triangles,
)


@pytest.fixture
def engine() -> HigherOrderKuramotoEngine:
    return HigherOrderKuramotoEngine(
        sigma1=1.0,
        sigma2=0.5,
        dt=0.01,
        steps=200,
        correlation_threshold=0.3,
    )


@pytest.fixture
def complete_corr_4():
    """K4 complete graph correlation."""
    n = 4
    corr = np.full((n, n), 0.8)
    np.fill_diagonal(corr, 1.0)
    return corr


class TestTriangleDetection:
    def test_complete_graph(self):
        """K4 has C(4,3) = 4 triangles."""
        adj = np.ones((4, 4), dtype=bool)
        np.fill_diagonal(adj, False)
        triangles = find_triangles(adj)
        assert len(triangles) == 4

    def test_path_graph_no_triangles(self):
        """Path graph 0-1-2-3 has no triangles."""
        adj = np.zeros((4, 4), dtype=bool)
        adj[0, 1] = adj[1, 0] = True
        adj[1, 2] = adj[2, 1] = True
        adj[2, 3] = adj[3, 2] = True
        triangles = find_triangles(adj)
        assert len(triangles) == 0

    def test_single_triangle(self):
        """Triangle 0-1-2."""
        adj = np.zeros((3, 3), dtype=bool)
        adj[0, 1] = adj[1, 0] = True
        adj[1, 2] = adj[2, 1] = True
        adj[0, 2] = adj[2, 0] = True
        triangles = find_triangles(adj)
        assert len(triangles) == 1
        assert triangles[0] == (0, 1, 2)


class TestTriangleIndex:
    def test_index_completeness(self):
        triangles = [(0, 1, 2)]
        index = build_triangle_index(3, triangles)
        assert len(index[0]) == 1
        assert len(index[1]) == 1
        assert len(index[2]) == 1


class TestHigherOrderDynamics:
    """Triadic coupling should produce different dynamics than pairwise only."""

    def test_valid_result(self, engine, complete_corr_4):
        result = engine.run(complete_corr_4, seed=42)
        assert isinstance(result, HigherOrderKuramotoResult)
        assert result.phases.shape == (201, 4)
        assert result.order_parameter.shape == (201,)
        assert result.time.shape == (201,)

    def test_R_bounded(self, engine, complete_corr_4):
        """INV-K1: R(t) ∈ [0, 1] for every step of the higher-order Kuramoto run.

        The order parameter is the modulus of a mean of unit-modulus
        complex numbers, so it is bounded in [0, 1] by definition. A
        violation here is not a numerical artefact — it means the
        triadic integrator corrupted the phase representation.
        """
        result = engine.run(complete_corr_4, seed=42)
        r_min = float(np.min(result.order_parameter))
        r_max = float(np.max(result.order_parameter))

        assert np.all(result.order_parameter >= 0), (
            f"INV-K1 VIOLATED: min R = {r_min:.6f} < 0. "
            f"Expected R ≥ 0 by definition (R = |mean(e^{{iθ}})|). "
            f"Observed at N=4, seed=42 with K_c-independent triadic σ₂=0.5. "
            f"Physical reasoning: modulus of a complex mean cannot be negative."
        )
        assert np.all(result.order_parameter <= 1), (
            f"INV-K1 VIOLATED: max R = {r_max:.6f} > 1. "
            f"Expected R ≤ 1 by Cauchy-Schwarz on unit phasors. "
            f"Observed at N=4, seed=42 with σ₁=1.0, σ₂=0.5. "
            f"Physical reasoning: |mean(z_i)| ≤ max|z_i| = 1 for unit |z_i|."
        )

    def test_finite_outputs(self, engine, complete_corr_4):
        """INV-HPC2: kernel produces finite outputs for finite bounded inputs.

        The correlation matrix is bounded in [-1, 1] and dt/σ are finite;
        any NaN/Inf in the output is a numerical-stability regression in
        the higher-order Kuramoto integrator (runaway phase or under/
        overflow in the triadic term).
        """
        result = engine.run(complete_corr_4, seed=42)
        n_bad_phases = int(np.sum(~np.isfinite(result.phases)))
        n_bad_r = int(np.sum(~np.isfinite(result.order_parameter)))
        n_bad_tri = int(np.sum(~np.isfinite(result.triadic_contribution)))

        assert np.all(np.isfinite(result.phases)), (
            f"INV-HPC2 VIOLATED: {n_bad_phases} non-finite phase entries. "
            f"Expected every phase finite for bounded correlation input. "
            f"Observed at N=4, seed=42, steps=200, dt=0.01. "
            f"Physical reasoning: Euler step on sin() of bounded phase "
            f"cannot diverge unless σ·dt destabilises the integrator."
        )
        assert np.all(np.isfinite(result.order_parameter)), (
            f"INV-HPC2 VIOLATED: {n_bad_r} non-finite R entries. "
            f"Expected finite R as mean of finite phasors. "
            f"Observed at N=4, seed=42, steps=200. "
            f"Physical reasoning: NaN in R means NaN already in phases upstream."
        )
        assert np.all(np.isfinite(result.triadic_contribution)), (
            f"INV-HPC2 VIOLATED: {n_bad_tri} non-finite triadic entries. "
            f"Expected finite σ₂ contribution for K4 (4 triangles, all weights 0.8). "
            f"Observed at N=4, seed=42, steps=200. "
            f"Physical reasoning: triadic term = σ₂ · Σ sin(θ_j + θ_k − 2θ_i), bounded."
        )

    def test_triangles_detected(self, engine, complete_corr_4):
        result = engine.run(complete_corr_4, seed=42)
        assert result.n_triangles == 4  # K4 has 4 triangles

    def test_triadic_contribution_nonzero(self, engine, complete_corr_4):
        """With triangles, σ₂ term should contribute."""
        result = engine.run(complete_corr_4, seed=42)
        assert np.max(result.triadic_contribution) > 0

    def test_no_triadic_for_tree(self, engine):
        """Tree graph (no triangles) → triadic contribution = 0."""
        # Path correlation: only adjacent pairs correlated
        n = 4
        corr = np.eye(n)
        corr[0, 1] = corr[1, 0] = 0.5
        corr[1, 2] = corr[2, 1] = 0.5
        corr[2, 3] = corr[3, 2] = 0.5

        result = engine.run(corr, seed=42)
        assert result.n_triangles == 0
        assert np.all(result.triadic_contribution == 0)


class TestPairwiseVsHigherOrder:
    """Higher-order should detect clusters pairwise misses."""

    def test_sigma2_affects_dynamics(self):
        corr = np.full((4, 4), 0.8)
        np.fill_diagonal(corr, 1.0)

        e_pair = HigherOrderKuramotoEngine(sigma1=1.0, sigma2=0.0, steps=200)
        e_both = HigherOrderKuramotoEngine(sigma1=1.0, sigma2=1.0, steps=200)

        r_pair = e_pair.run(corr, seed=42)
        r_both = e_both.run(corr, seed=42)

        # Dynamics should differ
        assert not np.allclose(r_pair.order_parameter, r_both.order_parameter, atol=0.01)


class TestFromPrices:
    def test_run_from_prices(self, engine):
        rng = np.random.default_rng(42)
        prices = 100 + np.cumsum(rng.normal(0, 1, (80, 5)), axis=0)
        result = engine.run_from_prices(prices, window=30, seed=42)
        assert isinstance(result, HigherOrderKuramotoResult)
        assert np.all(np.isfinite(result.order_parameter))


class TestDeterminism:
    def test_deterministic(self, engine, complete_corr_4):
        """INV-HPC1: bit-for-bit reproducibility under identical seed.

        Runs the same (seed, input, dtype) triple three times and asserts
        every pair of runs is bit-identical. Any divergence means
        non-determinism leaked into the integrator (uninitialised
        memory, hash-random ordering, or a non-seeded RNG branch).
        """
        n_runs = 3
        phase_runs = [engine.run(complete_corr_4, seed=42).phases for _ in range(n_runs)]
        baseline = phase_runs[0]
        for run_idx, other in enumerate(phase_runs[1:], start=1):
            max_ulp_diff = float(np.max(np.abs(other - baseline)))
            assert np.array_equal(other, baseline), (
                f"INV-HPC1 VIOLATED: run {run_idx} differs from run 0 "
                f"by up to {max_ulp_diff:.3e}. "
                f"Expected bit-identical phases under fixed seed=42. "
                f"Observed at N=4, steps=200, dt=0.01. "
                f"Physical reasoning: deterministic ODE + seeded RNG must replay identically."
            )


class TestInputValidation:
    def test_bad_dt(self):
        with pytest.raises(ValueError):
            HigherOrderKuramotoEngine(dt=0)

    def test_bad_steps(self):
        with pytest.raises(ValueError):
            HigherOrderKuramotoEngine(steps=0)


class TestSimplicialRepresentationHonesty:
    """Metamorphic locks for the declared unsigned 2-skeleton semantics.

    These tests do not change behaviour; they pin the *actual* semantics of
    the ``|ρ| > threshold`` structure-building step so the module cannot
    silently claim a signed simplicial model it does not implement. Sign
    erasure is asserted-and-declared rather than hidden.
    """

    def test_provenance_fields_declare_unsigned_higher_order(self) -> None:
        engine = HigherOrderKuramotoEngine(
            sigma1=1.0, sigma2=0.5, dt=0.01, steps=20, correlation_threshold=0.3
        )
        n = 4
        corr = np.full((n, n), 0.8)
        np.fill_diagonal(corr, 1.0)
        result = engine.run(corr, seed=1)
        assert result.signed is False
        assert result.higher_order is True
        assert result.representation == "simplicial_2skeleton"
        assert "correlation_sign" in result.information_loss
        assert "triadic_edge_weight" in result.information_loss

    def test_sign_erasure_is_recorded_dynamics_identical(self) -> None:
        # |ρ| > threshold and the |ρ|-weighted RHS are sign-independent, so a
        # full sign flip of the correlation matrix yields bit-identical
        # dynamics. This information loss must be declared (signed=False /
        # "correlation_sign"), not silently produce a "signed simplicial" claim.
        engine = HigherOrderKuramotoEngine(
            sigma1=1.0, sigma2=0.5, dt=0.01, steps=50, correlation_threshold=0.3
        )
        n = 4
        pos = np.full((n, n), 0.8)
        np.fill_diagonal(pos, 1.0)
        neg = -pos.copy()
        np.fill_diagonal(neg, 1.0)  # keep unit diagonal; off-diagonal ρ -> -ρ
        r_pos = engine.run(pos, seed=7)
        r_neg = engine.run(neg, seed=7)
        np.testing.assert_array_equal(r_pos.phases, r_neg.phases)
        np.testing.assert_array_equal(r_pos.order_parameter, r_neg.order_parameter)
        assert r_pos.n_triangles == r_neg.n_triangles
        assert r_pos.signed is False
        assert "correlation_sign" in r_pos.information_loss

    def test_triadic_term_is_not_pairwise_reducible(self) -> None:
        # The higher-order claim that survives: with triangles present, the
        # σ₂ triadic term changes the trajectory vs σ₂=0. This is the genuine
        # (non-erased) part of the model and must stay true.
        n = 4
        corr = np.full((n, n), 0.8)
        np.fill_diagonal(corr, 1.0)
        with_tri = HigherOrderKuramotoEngine(
            sigma1=1.0, sigma2=0.8, dt=0.01, steps=80, correlation_threshold=0.3
        ).run(corr, seed=3)
        no_tri = HigherOrderKuramotoEngine(
            sigma1=1.0, sigma2=0.0, dt=0.01, steps=80, correlation_threshold=0.3
        ).run(corr, seed=3)
        assert with_tri.n_triangles > 0
        assert not np.array_equal(with_tri.order_parameter, no_tri.order_parameter)
