# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T1 — Gravitational Coupling Matrix tests.

Every test is a falsifiable assertion derived from AGENT-MATH sign-off.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.physics.gravitational_coupling import GravitationalCouplingMatrix


@pytest.fixture
def gcm() -> GravitationalCouplingMatrix:
    return GravitationalCouplingMatrix(window=5, clip_sigma=3.0)


@pytest.fixture
def two_asset_data():
    """Minimal 2-asset system with known analytical properties."""
    rng = np.random.default_rng(42)
    T = 50
    prices = np.column_stack(
        [
            100 + np.cumsum(rng.normal(0, 1, T)),
            200 + np.cumsum(rng.normal(0, 1, T)),
        ]
    )
    volumes = rng.uniform(100, 1000, (T, 2))
    return prices, volumes


class TestGravitationalMatrixSymmetry:
    """F_ij = F_ji because gravitational force is symmetric."""

    def test_output_is_symmetric(self, gcm, two_asset_data):
        prices, volumes = two_asset_data
        A = gcm.compute(prices, volumes)
        np.testing.assert_allclose(A, A.T, atol=1e-12)

    def test_diagonal_is_zero(self, gcm, two_asset_data):
        prices, volumes = two_asset_data
        A = gcm.compute(prices, volumes)
        np.testing.assert_array_equal(np.diag(A), 0.0)

    def test_multi_asset_symmetric(self, gcm):
        rng = np.random.default_rng(7)
        T, N = 60, 5
        prices = 100 + np.cumsum(rng.normal(0, 0.5, (T, N)), axis=0)
        volumes = rng.uniform(50, 500, (T, N))
        A = gcm.compute(prices, volumes)
        np.testing.assert_allclose(A, A.T, atol=1e-12)
        assert A.shape == (N, N)


class TestReducesToUniform:
    """For equal liquidity assets with zero correlation distance → uniform coupling."""

    def test_equal_volume_equal_correlation(self):
        gcm = GravitationalCouplingMatrix(window=5)
        T, N = 50, 3
        # All assets have identical volume
        prices = np.tile(np.linspace(100, 110, T).reshape(-1, 1), (1, N))
        # Add tiny noise to avoid degenerate correlation
        rng = np.random.default_rng(0)
        prices += rng.normal(0, 0.01, prices.shape)
        volumes = np.ones((T, N)) * 500.0

        A = gcm.compute(prices, volumes)
        # All off-diagonal should be approximately equal
        off_diag = A[~np.eye(N, dtype=bool)]
        assert np.std(off_diag) < 0.1, f"Non-uniform coupling: std={np.std(off_diag)}"


class TestKuramotoStabilityPreserved:
    """Gravitational coupling preserves Kuramoto stability conditions."""

    def test_adjacency_non_negative(self, gcm, two_asset_data):
        prices, volumes = two_asset_data
        A = gcm.compute(prices, volumes)
        assert np.all(A >= 0), "Adjacency must be non-negative"

    def test_adjacency_finite(self, gcm, two_asset_data):
        prices, volumes = two_asset_data
        A = gcm.compute(prices, volumes)
        assert np.all(np.isfinite(A)), "Adjacency must be finite (clipping works)"

    def test_works_with_kuramoto_config(self, gcm, two_asset_data):
        """Integration test: adjacency passes KuramotoConfig validation."""
        from core.kuramoto.config import KuramotoConfig

        prices, volumes = two_asset_data
        A = gcm.compute(prices, volumes)
        N = A.shape[0]
        config = KuramotoConfig(N=N, K=1.0, adjacency=A, seed=42)
        assert config.coupling_mode == "adjacency"


class TestKnownCase:
    """2-asset system: analytical solution verifiable."""

    def test_two_asset_analytical(self):
        gcm = GravitationalCouplingMatrix(window=5, clip_sigma=3.0)
        T = 30
        rng = np.random.default_rng(99)
        # Asset 1: high volume, Asset 2: low volume
        prices = np.column_stack(
            [
                100 + np.cumsum(rng.normal(0, 1, T)),
                100 + np.cumsum(rng.normal(0, 1, T)),
            ]
        )
        volumes = np.column_stack(
            [
                np.full(T, 1000.0),
                np.full(T, 100.0),
            ]
        )
        A = gcm.compute(prices, volumes)
        # With asymmetric mass, after normalisation+symmetrisation
        # we still get a valid symmetric matrix
        np.testing.assert_allclose(A, A.T, atol=1e-12)
        assert A[0, 1] > 0, "Off-diagonal must be positive"


class TestInputValidation:
    def test_rejects_1d_input(self, gcm):
        with pytest.raises(ValueError, match="2-D"):
            gcm.compute(np.array([1, 2, 3]), np.array([1, 2, 3]))

    def test_rejects_shape_mismatch(self, gcm):
        with pytest.raises(ValueError, match="same shape"):
            gcm.compute(np.ones((10, 2)), np.ones((10, 3)))

    def test_rejects_single_asset(self, gcm):
        with pytest.raises(ValueError, match="≥ 2"):
            gcm.compute(np.ones((10, 1)), np.ones((10, 1)))


def test_correlation_structure_drives_coupling_strength(gcm) -> None:
    """`if prices.shape[0] < 2` guards the correlation-distance estimator (INV-T1).

    Under `Lt -> GtE` a full price history is treated as too-short and every distance collapses
    to 1.0, so the coupling matrix depends only on mass and loses all correlation structure. Two
    co-moving assets must couple far more strongly than either does to an independent one.
    """
    import numpy as np

    rng = np.random.default_rng(0)
    T = 30
    factor = rng.standard_normal(T)
    a = np.cumsum(factor + 0.02 * rng.standard_normal(T)) + 100.0
    b = np.cumsum(factor + 0.02 * rng.standard_normal(T)) + 100.0  # co-moves with a
    c = np.cumsum(rng.standard_normal(T)) + 100.0  # independent
    prices = np.column_stack([a, b, c])
    volumes = np.full((T, 3), 500.0)  # equal mass -> only correlation can differentiate

    matrix = gcm.compute(prices, volumes)
    assert matrix[0, 1] > 2.0 * matrix[0, 2], (
        "co-moving assets did not couple more strongly than the independent one -- "
        "correlation structure was lost"
    )


def test_outlier_clip_actually_reshapes_the_coupling() -> None:
    """`if upper.size > 0` / `if f_max > 0` gate the outlier clip (robustness).

    Rule-Zero note: the clip is an OUTLIER-ROBUSTNESS guarantee, not a physics
    law -- a cluster of spurious high forces must not dominate the coupling. A
    single dominant outlier is absorbed by row-normalisation (equivalent there),
    but MULTIPLE moderate outliers are flattened by the clip, changing the
    normalised result. Under Gt->LtE both guards skip the clip entirely (f_max is
    always > 0 for non-negative forces), so a tight clip_sigma and a loose one
    would produce identical output -- the robustness guarantee silently gone.
    """
    rng = np.random.default_rng(7)
    T, N = 80, 8
    prices = 100.0 + np.cumsum(rng.standard_normal((T, N)) * 0.4, axis=0)
    volumes = np.abs(rng.standard_normal((T, N))) * 100.0 + 200.0
    for k in (0, 1, 2):
        volumes[:, k] *= 30.0
    prices[:, 1] = 0.7 * prices[:, 0] + 0.3 * prices[:, 1]
    prices[:, 2] = 0.6 * prices[:, 0] + 0.4 * prices[:, 2]

    tight = GravitationalCouplingMatrix(window=30, clip_sigma=2.0).compute(prices, volumes)
    loose = GravitationalCouplingMatrix(window=30, clip_sigma=1e12).compute(prices, volumes)
    # Clipping is active and reshapes the coupling; the mutant (never clip) would
    # make these byte-identical.
    assert not np.allclose(tight, loose)
