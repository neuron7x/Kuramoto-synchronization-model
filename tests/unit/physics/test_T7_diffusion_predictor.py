# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T7 — Graph diffusion volatility front predictor tests."""

import numpy as np
import pytest

from core.physics.diffusion_predictor import (
    DiffusionVolatilityPredictor,
    VolatilityFrontPrediction,
)


@pytest.fixture
def predictor() -> DiffusionVolatilityPredictor:
    return DiffusionVolatilityPredictor(D_0=1.0, threshold_quantile=0.75)


@pytest.fixture
def simple_adjacency():
    """5-asset chain: 0—1—2—3—4."""
    n = 5
    adj = np.zeros((n, n))
    for i in range(n - 1):
        adj[i, i + 1] = adj[i + 1, i] = 0.5
    return adj


class TestVolatilityPropagation:
    """Volatility should spread from source along edges."""

    def test_front_from_single_source(self, predictor, simple_adjacency):
        vol = np.array([1.0, 0.0, 0.0, 0.0, 0.0])
        pred = predictor.predict(vol, simple_adjacency)
        assert isinstance(pred, VolatilityFrontPrediction)
        # After propagation, density should spread from node 0
        assert pred.density_t1[0] > 0
        assert pred.density_t1[1] > pred.density_t1[4]  # closer gets more

    def test_probability_conservation(self, predictor, simple_adjacency):
        vol = np.array([0.5, 0.2, 0.1, 0.1, 0.1])
        pred = predictor.predict(vol, simple_adjacency)
        assert abs(pred.density_t1.sum() - 1.0) < 1e-10
        assert abs(pred.density_t3.sum() - 1.0) < 1e-10

    def test_longer_horizon_more_diffused(self, predictor, simple_adjacency):
        vol = np.array([1.0, 0.0, 0.0, 0.0, 0.0])
        pred = predictor.predict(vol, simple_adjacency)
        # At t=3, density should be more spread than t=1
        std_t1 = np.std(pred.density_t1)
        std_t3 = np.std(pred.density_t3)
        assert std_t3 < std_t1, "Longer time → more uniform → lower std"


class TestCurvatureEffect:
    """Positive curvature → faster diffusion."""

    def test_positive_curvature_spreads_faster(self, predictor, simple_adjacency):
        vol = np.array([1.0, 0.0, 0.0, 0.0, 0.0])
        n = simple_adjacency.shape[0]

        curv_pos = np.full((n, n), 1.0)
        np.fill_diagonal(curv_pos, 0.0)
        curv_neg = np.full((n, n), -1.0)
        np.fill_diagonal(curv_neg, 0.0)

        pred_pos = predictor.predict(vol, simple_adjacency, curv_pos)
        pred_neg = predictor.predict(vol, simple_adjacency, curv_neg)

        # Positive curvature → node 0 loses density faster
        assert pred_pos.density_t1[0] < pred_neg.density_t1[0]


class TestFrontDetection:
    def test_front_indices(self, predictor, simple_adjacency):
        vol = np.array([1.0, 0.0, 0.0, 0.0, 0.0])
        pred = predictor.predict(vol, simple_adjacency)
        assert isinstance(pred.predicted_front, list)
        assert len(pred.predicted_front) > 0

    def test_threshold_affects_front_size(self):
        p_strict = DiffusionVolatilityPredictor(threshold_quantile=0.9)
        p_loose = DiffusionVolatilityPredictor(threshold_quantile=0.5)

        adj = np.ones((4, 4)) * 0.5
        np.fill_diagonal(adj, 0.0)
        vol = np.array([0.5, 0.3, 0.1, 0.1])

        front_strict = p_strict.predict(vol, adj).predicted_front
        front_loose = p_loose.predict(vol, adj).predicted_front
        assert len(front_strict) <= len(front_loose)


class TestBacktest:
    def test_basic_backtest(self, predictor):
        rng = np.random.default_rng(42)
        prices = 100 + np.cumsum(rng.normal(0, 1, (100, 5)), axis=0)

        result = predictor.backtest(
            prices,
            vol_window=5,
            correlation_window=15,
        )
        assert result.n_windows > 0
        assert 0 <= result.roc_auc_t1 <= 1
        assert 0 <= result.roc_auc_t3 <= 1
        assert 0 <= result.precision_t1 <= 1
        assert 0 <= result.recall_t1 <= 1

    def test_insufficient_data(self, predictor):
        result = predictor.backtest(np.ones((10, 3)))
        assert result.n_windows == 0
        assert result.roc_auc_t1 == 0.5  # random baseline


class TestDeterminism:
    def test_deterministic(self, predictor, simple_adjacency):
        vol = np.array([0.5, 0.3, 0.1, 0.05, 0.05])
        p1 = predictor.predict(vol, simple_adjacency)
        p2 = predictor.predict(vol, simple_adjacency)
        np.testing.assert_array_equal(p1.density_t1, p2.density_t1)


class TestInputValidation:
    def test_bad_D0(self):
        with pytest.raises(ValueError):
            DiffusionVolatilityPredictor(D_0=0)

    def test_bad_quantile(self):
        with pytest.raises(ValueError):
            DiffusionVolatilityPredictor(threshold_quantile=0)


class TestNonFickian:
    """Pin the corrected claim: the operator is NOT free physical diffusion.

    The module evolves ρ(t)=R(exp(-Lt)·ρ₀) on a FINITE graph. Free Fickian
    diffusion on an unbounded medium has mean-square displacement ⟨x²⟩∝t
    (scaling exponent 1) without bound. On a finite line the heat kernel
    cannot spread past the end nodes: ρ relaxes to the (uniform) stationary
    distribution and the MSD SATURATES — the long-horizon log-log exponent
    collapses toward 0, NOT 1. The simplex projection R is a near-no-op for
    valid inputs (verified separately); the saturation is the finite-graph
    boundary. This test fails if a future change makes the operator behave
    like unbounded Fickian diffusion, re-asserting the "diffusion" mislabel.
    """

    @staticmethod
    def _msd(densities, positions):
        """Mean-square displacement per horizon.

        MSD(t) = Σ_i p_i(t) · (x_i − x̄(t))²  with x̄(t) = Σ_i p_i(t)·x_i.
        """
        out = np.empty(len(densities), dtype=np.float64)
        for k, rho in enumerate(densities):
            mean_x = float(np.sum(rho * positions))
            out[k] = float(np.sum(rho * (positions - mean_x) ** 2))
        return out

    @staticmethod
    def _line_predictor(n):
        adj = np.zeros((n, n))
        for i in range(n - 1):
            adj[i, i + 1] = adj[i + 1, i] = 1.0
        predictor = DiffusionVolatilityPredictor(D_0=1.0)
        laplacian = predictor._build_laplacian(adj, None)
        return predictor, laplacian

    def test_renorm_is_noop_for_valid_inputs(self):
        # Documents that R(·) is a near-no-op (machine precision) for a
        # valid Laplacian + non-negative simplex input: the heat kernel
        # already conserves mass and is non-negative, so it is NOT the
        # renorm that makes the operator non-Fickian.
        n = 41
        predictor, laplacian = self._line_predictor(n)
        from scipy.linalg import expm

        rho_0 = np.zeros(n)
        rho_0[n // 2] = 1.0
        horizons = [1.0, 8.0, 64.0, 512.0]
        max_diff = 0.0
        for t in horizons:
            free = expm(-laplacian * t) @ rho_0
            renorm = predictor._propagate(rho_0, laplacian, t)
            max_diff = max(max_diff, float(np.max(np.abs(free - renorm))))
        assert max_diff < 1e-9, (
            f"RENORM-NOOP VIOLATED: |R(exp(-Lt)ρ₀) − exp(-Lt)ρ₀|_max="
            f"{max_diff:.3e} ≥ 1e-9, so the renorm is NOT a no-op here. "
            f"Expected machine-precision agreement: a graph heat kernel "
            f"conserves mass and stays ≥0 for simplex inputs. "
            f"line graph N={n}, horizons={horizons}"
        )

    def test_msd_saturates_not_fickian(self):
        # Long line graph; point source at the centre. Sample the
        # SATURATION regime (front has reached the boundary), where the
        # relaxation departs hardest from Fickian ⟨x²⟩∝t.
        n = 41
        predictor, laplacian = self._line_predictor(n)
        positions = np.arange(n, dtype=np.float64)

        rho_0 = np.zeros(n)
        rho_0[n // 2] = 1.0

        horizons = [64.0, 128.0, 256.0, 512.0, 1024.0]
        densities = [predictor._propagate(rho_0, laplacian, t) for t in horizons]

        # Every propagated state stays a valid simplex ranking (Σρ=1).
        for t, rho in zip(horizons, densities, strict=True):
            assert abs(rho.sum() - 1.0) < 1e-9, (
                f"NON-FICKIAN-PIN VIOLATED: propagated score at t={t:.1f} "
                f"sums to {rho.sum():.6e}, expected 1.0 within 1e-9. "
                f"The output must remain a ranking on the probability simplex. "
                f"line graph N={n}, centre source. "
                f"If this fails the propagator no longer normalises."
            )

        msd = self._msd(densities, positions)
        slope = float(np.polyfit(np.log(horizons), np.log(msd), 1)[0])

        # Free Fickian diffusion ⇒ slope ≈ 1. The finite-graph relaxation
        # saturates ⇒ slope must be far below 1 (measured ≈ 0.1).
        fickian_exponent = 1.0
        non_fickian_ceiling = 0.3
        assert slope < non_fickian_ceiling, (
            f"NON-FICKIAN-PIN VIOLATED: saturation-regime MSD exponent="
            f"{slope:.4f} ≥ ceiling={non_fickian_ceiling:.2f}, i.e. it "
            f"looks Fickian (exponent {fickian_exponent:.1f} ⇒ ⟨x²⟩∝t). "
            f"A finite-graph relaxation must SATURATE, not diffuse freely. "
            f"line graph N={n}, horizons={horizons}, MSD={np.round(msd, 3).tolist()}"
        )

        # And the MSD must actually plateau: last step grows < 1% — a
        # positive statement that it has reached the stationary variance.
        plateau_growth = float(msd[-1] / msd[-2] - 1.0)
        assert plateau_growth < 0.01, (
            f"NON-FICKIAN-PIN VIOLATED: MSD still growing "
            f"{plateau_growth * 100:.2f}% between the last two horizons, "
            f"expected <1% (plateau at stationary variance). "
            f"A saturating relaxation must stop spreading. "
            f"line graph N={n}, MSD_tail={np.round(msd[-2:], 4).tolist()}"
        )
