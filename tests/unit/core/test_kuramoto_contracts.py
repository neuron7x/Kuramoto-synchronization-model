# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for ``core.kuramoto.contracts`` (protocol M1.1).

Covers:
- Frozen-dataclass attribute reassignment guard.
- Deep immutability (array ``flags.writeable = False``).
- Defensive copy on construction (caller-held reference cannot mutate).
- Shape, dtype and range validation for every contract.
- Cross-contract ``asset_ids`` consistency in ``NetworkState``.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from core.kuramoto.contracts import (
    CouplingMatrix,
    DelayMatrix,
    EmergentMetrics,
    FrustrationMatrix,
    NetworkState,
    PhaseMatrix,
    SyntheticGroundTruth,
    _freeze_array,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ids() -> tuple[str, ...]:
    return ("A", "B", "C")


@pytest.fixture()
def phase_matrix(ids: tuple[str, ...]) -> PhaseMatrix:
    rng = np.random.default_rng(0)
    T, N = 50, len(ids)
    theta = np.mod(rng.uniform(0.0, 2 * np.pi, size=(T, N)), 2 * np.pi)
    return PhaseMatrix(
        theta=theta,
        timestamps=np.arange(T, dtype=np.float64),
        asset_ids=ids,
        extraction_method="hilbert",
        frequency_band=(0.05, 0.2),
        amplitude=np.ones((T, N)),
    )


@pytest.fixture()
def coupling_matrix(ids: tuple[str, ...]) -> CouplingMatrix:
    K = np.array(
        [
            [0.0, 0.5, -0.3],
            [0.4, 0.0, 0.2],
            [-0.1, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    return CouplingMatrix(K=K, asset_ids=ids, sparsity=1 / 9, method="scad")


@pytest.fixture()
def delay_matrix(ids: tuple[str, ...]) -> DelayMatrix:
    tau = np.array([[0, 2, 1], [1, 0, 0], [0, 1, 0]], dtype=np.int64)
    return DelayMatrix(
        tau=tau,
        tau_seconds=tau.astype(np.float64) * 60.0,
        asset_ids=ids,
        method="cross_correlation",
        max_lag_tested=5,
    )


@pytest.fixture()
def frustration_matrix(ids: tuple[str, ...]) -> FrustrationMatrix:
    alpha = np.zeros((3, 3), dtype=np.float64)
    alpha[0, 1] = 0.3
    alpha[1, 0] = -0.3
    return FrustrationMatrix(alpha=alpha, asset_ids=ids, method="profile_likelihood")


# ---------------------------------------------------------------------------
# _freeze_array primitive
# ---------------------------------------------------------------------------


def test_freeze_array_returns_none_for_none() -> None:
    assert _freeze_array(None) is None


def test_freeze_array_is_defensive_copy() -> None:
    src = np.array([1.0, 2.0, 3.0])
    frozen = _freeze_array(src)
    assert frozen is not None
    # Mutating the original must NOT affect the frozen copy
    src[0] = 999.0
    assert frozen[0] == 1.0
    # Frozen copy is write-protected
    assert frozen.flags.writeable is False
    with pytest.raises(ValueError):
        frozen[0] = 42.0


# ---------------------------------------------------------------------------
# PhaseMatrix
# ---------------------------------------------------------------------------


class TestPhaseMatrix:
    def test_theta_is_write_protected(self, phase_matrix: PhaseMatrix) -> None:
        assert phase_matrix.theta.flags.writeable is False
        with pytest.raises(ValueError):
            phase_matrix.theta[0, 0] = 0.0

    def test_frozen_attribute_reassignment_blocked(self, phase_matrix: PhaseMatrix) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            phase_matrix.extraction_method = "ssq_cwt"  # type: ignore[misc]

    def test_defensive_copy_on_init(self, ids: tuple[str, ...]) -> None:
        theta = np.zeros((10, 3), dtype=np.float64)
        pm = PhaseMatrix(
            theta=theta,
            timestamps=np.arange(10, dtype=np.float64),
            asset_ids=ids,
            extraction_method="hilbert",
            frequency_band=(0.05, 0.2),
        )
        # External mutation of the source array must not leak in
        theta[0, 0] = 1.5
        assert pm.theta[0, 0] == 0.0

    def test_rejects_non_float64(self, ids: tuple[str, ...]) -> None:
        with pytest.raises(ValueError, match="float64"):
            PhaseMatrix(
                theta=np.zeros((10, 3), dtype=np.float32),
                timestamps=np.arange(10),
                asset_ids=ids,
                extraction_method="hilbert",
                frequency_band=(0.05, 0.2),
            )

    def test_rejects_out_of_range_theta(self, ids: tuple[str, ...]) -> None:
        theta = np.full((10, 3), 7.0, dtype=np.float64)  # > 2π
        with pytest.raises(ValueError, match=r"\[0, 2π\)"):
            PhaseMatrix(
                theta=theta,
                timestamps=np.arange(10, dtype=np.float64),
                asset_ids=ids,
                extraction_method="hilbert",
                frequency_band=(0.05, 0.2),
            )

    def test_rejects_duplicate_asset_ids(self) -> None:
        with pytest.raises(ValueError, match="unique"):
            PhaseMatrix(
                theta=np.zeros((10, 3), dtype=np.float64),
                timestamps=np.arange(10, dtype=np.float64),
                asset_ids=("A", "A", "B"),
                extraction_method="hilbert",
                frequency_band=(0.05, 0.2),
            )

    def test_rejects_bad_method(self, ids: tuple[str, ...]) -> None:
        with pytest.raises(ValueError, match="extraction_method"):
            PhaseMatrix(
                theta=np.zeros((10, 3), dtype=np.float64),
                timestamps=np.arange(10, dtype=np.float64),
                asset_ids=ids,
                extraction_method="wavelet",  # invalid
                frequency_band=(0.05, 0.2),
            )

    def test_rejects_inverted_band(self, ids: tuple[str, ...]) -> None:
        with pytest.raises(ValueError, match="frequency_band"):
            PhaseMatrix(
                theta=np.zeros((10, 3), dtype=np.float64),
                timestamps=np.arange(10, dtype=np.float64),
                asset_ids=ids,
                extraction_method="hilbert",
                frequency_band=(0.3, 0.1),
            )

    def test_convenience_properties(self, phase_matrix: PhaseMatrix) -> None:
        assert phase_matrix.T == 50
        assert phase_matrix.N == 3


# ---------------------------------------------------------------------------
# CouplingMatrix
# ---------------------------------------------------------------------------


class TestCouplingMatrix:
    def test_diagonal_must_be_zero(self, ids: tuple[str, ...]) -> None:
        K = np.eye(3, dtype=np.float64)
        with pytest.raises(ValueError, match="diagonal"):
            CouplingMatrix(K=K, asset_ids=ids, sparsity=0.0, method="scad")

    def test_rejects_bad_sparsity(self, ids: tuple[str, ...]) -> None:
        K = np.zeros((3, 3), dtype=np.float64)
        with pytest.raises(ValueError, match="sparsity"):
            CouplingMatrix(K=K, asset_ids=ids, sparsity=1.5, method="scad")

    def test_nonzero_mask(self, coupling_matrix: CouplingMatrix) -> None:
        mask = coupling_matrix.nonzero_mask()
        assert mask.dtype == bool
        assert mask.sum() == 5

    def test_stability_scores_range(self, ids: tuple[str, ...]) -> None:
        K = np.zeros((3, 3), dtype=np.float64)
        with pytest.raises(ValueError, match="stability_scores"):
            CouplingMatrix(
                K=K,
                asset_ids=ids,
                sparsity=1.0,
                method="scad",
                stability_scores=np.full((3, 3), 1.5),
            )

    def test_rejects_non_finite(self, ids: tuple[str, ...]) -> None:
        K = np.zeros((3, 3), dtype=np.float64)
        K[0, 1] = np.nan
        with pytest.raises(ValueError, match="NaN"):
            CouplingMatrix(K=K, asset_ids=ids, sparsity=1.0, method="scad")


# ---------------------------------------------------------------------------
# DelayMatrix
# ---------------------------------------------------------------------------


class TestDelayMatrix:
    def test_rejects_float_tau(self, ids: tuple[str, ...]) -> None:
        with pytest.raises(ValueError, match="integer"):
            DelayMatrix(
                tau=np.zeros((3, 3), dtype=np.float64),
                tau_seconds=np.zeros((3, 3)),
                asset_ids=ids,
                method="cross_correlation",
                max_lag_tested=5,
            )

    def test_rejects_negative_tau(self, ids: tuple[str, ...]) -> None:
        tau = np.zeros((3, 3), dtype=np.int64)
        tau[0, 1] = -1
        with pytest.raises(ValueError, match="non-negative"):
            DelayMatrix(
                tau=tau,
                tau_seconds=tau.astype(np.float64),
                asset_ids=ids,
                method="cross_correlation",
                max_lag_tested=5,
            )

    def test_rejects_tau_over_max(self, ids: tuple[str, ...]) -> None:
        tau = np.zeros((3, 3), dtype=np.int64)
        tau[0, 1] = 10
        with pytest.raises(ValueError, match="max_lag_tested"):
            DelayMatrix(
                tau=tau,
                tau_seconds=tau.astype(np.float64),
                asset_ids=ids,
                method="cross_correlation",
                max_lag_tested=5,
            )


# ---------------------------------------------------------------------------
# FrustrationMatrix
# ---------------------------------------------------------------------------


class TestFrustrationMatrix:
    def test_rejects_out_of_range(self, ids: tuple[str, ...]) -> None:
        alpha = np.zeros((3, 3), dtype=np.float64)
        alpha[0, 1] = 4.0  # > π
        with pytest.raises(ValueError, match=r"\[-π, π\]"):
            FrustrationMatrix(alpha=alpha, asset_ids=ids, method="profile_likelihood")


# ---------------------------------------------------------------------------
# NetworkState
# ---------------------------------------------------------------------------


class TestNetworkState:
    def test_happy_path(
        self,
        phase_matrix: PhaseMatrix,
        coupling_matrix: CouplingMatrix,
        delay_matrix: DelayMatrix,
        frustration_matrix: FrustrationMatrix,
    ) -> None:
        state = NetworkState(
            phases=phase_matrix,
            coupling=coupling_matrix,
            delays=delay_matrix,
            frustration=frustration_matrix,
            natural_frequencies=np.array([0.1, 0.12, 0.11], dtype=np.float64),
            noise_std=0.01,
        )
        assert state.N == 3
        assert state.asset_ids == ("A", "B", "C")

    def test_rejects_asset_id_mismatch(
        self,
        phase_matrix: PhaseMatrix,
        delay_matrix: DelayMatrix,
        frustration_matrix: FrustrationMatrix,
    ) -> None:
        bad = CouplingMatrix(
            K=np.zeros((3, 3), dtype=np.float64),
            asset_ids=("X", "Y", "Z"),
            sparsity=1.0,
            method="scad",
        )
        with pytest.raises(ValueError, match="asset_ids"):
            NetworkState(
                phases=phase_matrix,
                coupling=bad,
                delays=delay_matrix,
                frustration=frustration_matrix,
                natural_frequencies=np.array([0.1, 0.1, 0.1], dtype=np.float64),
                noise_std=0.01,
            )

    def test_rejects_negative_noise(
        self,
        phase_matrix: PhaseMatrix,
        coupling_matrix: CouplingMatrix,
        delay_matrix: DelayMatrix,
        frustration_matrix: FrustrationMatrix,
    ) -> None:
        with pytest.raises(ValueError, match="noise_std"):
            NetworkState(
                phases=phase_matrix,
                coupling=coupling_matrix,
                delays=delay_matrix,
                frustration=frustration_matrix,
                natural_frequencies=np.array([0.1, 0.1, 0.1], dtype=np.float64),
                noise_std=-0.1,
            )


# ---------------------------------------------------------------------------
# EmergentMetrics
# ---------------------------------------------------------------------------


class TestEmergentMetrics:
    def test_happy_path(self) -> None:
        T = 20
        em = EmergentMetrics(
            R_global=np.linspace(0.2, 0.9, T),
            R_cluster={0: np.full(T, 0.5), 1: np.full(T, 0.7)},
            metastability=0.05,
            chimera_index=np.zeros(T),
            csd_variance=np.zeros(T),
            csd_autocorr=np.zeros(T),
            edge_entropy=0.3,
            cluster_assignments=np.array([0, 0, 1], dtype=np.int64),
        )
        assert em.R_global.flags.writeable is False
        assert em.metastability == 0.05

    def test_rejects_out_of_range_R(self) -> None:
        with pytest.raises(ValueError, match="R_global"):
            EmergentMetrics(
                R_global=np.array([0.5, 1.5, 0.7]),
                R_cluster={},
                metastability=0.0,
                chimera_index=np.zeros(3),
                csd_variance=np.zeros(3),
                csd_autocorr=np.zeros(3),
                edge_entropy=0.0,
                cluster_assignments=np.array([0], dtype=np.int64),
            )


# ---------------------------------------------------------------------------
# SyntheticGroundTruth
# ---------------------------------------------------------------------------


class TestSyntheticGroundTruth:
    def test_happy_path(self, phase_matrix: PhaseMatrix) -> None:
        N = phase_matrix.N
        gt = SyntheticGroundTruth(
            true_K=np.zeros((N, N), dtype=np.float64),
            true_tau=np.zeros((N, N), dtype=np.int64),
            true_alpha=np.zeros((N, N), dtype=np.float64),
            true_omega=np.ones(N, dtype=np.float64),
            generated_phases=phase_matrix,
            noise_realizations=np.zeros((10, N), dtype=np.float64),
        )
        assert gt.true_K.flags.writeable is False
