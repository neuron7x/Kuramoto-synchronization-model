# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T7 — Landauer Bound tests.

Physical, not metaphor. Honest documentation of 9 OOM gap.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.physics.landauer import (
    K_BOLTZMANN,
    LANDAUER_ENERGY,
    ROOM_TEMPERATURE,
    LandauerInferenceProfiler,
)


@pytest.fixture
def profiler() -> LandauerInferenceProfiler:
    return LandauerInferenceProfiler(T=ROOM_TEMPERATURE, gpu_energy_per_op=1e-12)


class TestLandauerBoundCorrectAt300K:
    """Verify kT·ln(2) computation at room temperature."""

    def test_landauer_energy_value(self):
        expected = K_BOLTZMANN * 300.0 * math.log(2)
        assert abs(LANDAUER_ENERGY - expected) < 1e-30
        # Should be approximately 2.87 × 10⁻²¹ J
        assert 2.8e-21 < LANDAUER_ENERGY < 2.9e-21

    def test_profiler_per_bit(self, profiler):
        assert abs(profiler.landauer_per_bit - LANDAUER_ENERGY) < 1e-30


class TestSparseModelLowerEntropy:
    """Sparse model generates less entropy than dense model."""

    def test_sparse_less_entropy(self, profiler):
        S_sparse = profiler.entropy_per_step(100)
        S_dense = profiler.entropy_per_step(10000)
        assert S_sparse < S_dense

    def test_zero_params_zero_entropy(self, profiler):
        assert profiler.entropy_per_step(0) == 0.0


class TestEfficiencyIncreasesWithPruning:
    """Pruning: fewer params → less entropy → higher efficiency for same accuracy."""

    def test_pruning_improves_efficiency(self, profiler):
        accuracy = 0.8
        eff_dense = profiler.efficiency(accuracy, 10000)
        eff_sparse = profiler.efficiency(accuracy, 100)
        assert eff_sparse > eff_dense

    def test_zero_accuracy_zero_efficiency(self, profiler):
        assert profiler.efficiency(0.0, 1000) == 0.0


class TestLandauerRatio:
    """GPU operates ~10⁹ above Landauer limit."""

    def test_ratio_order_of_magnitude(self, profiler):
        ratio = profiler.landauer_ratio(1000)
        # gpu_energy = 1e-12, landauer = ~3e-21 → ratio ≈ 3.3e8
        assert 1e8 < ratio < 1e10, f"Expected ~10⁹, got {ratio:.2e}"


class TestMinimumEnergy:
    def test_scales_linearly(self, profiler):
        E1 = profiler.minimum_energy(100)
        E2 = profiler.minimum_energy(200)
        assert abs(E2 / E1 - 2.0) < 1e-10

    def test_actual_energy_larger(self, profiler):
        E_min = profiler.minimum_energy(1000)
        E_actual = profiler.actual_energy(1000)
        assert E_actual > E_min, "GPU energy must exceed Landauer minimum"


class TestPruningRecommendation:
    def test_recommend_pruning(self, profiler):
        importances = np.array([0.1, 0.5, 0.9, 0.3, 0.8])
        result = profiler.recommend_pruning(
            importances,
            target_efficiency=0.01,
            current_accuracy=0.8,
        )
        assert result["n_total"] == 5
        assert result["n_keep"] <= 5
        assert result["n_prune"] >= 0
        assert 0.0 <= result["prune_ratio"] <= 1.0

    def test_empty_params(self, profiler):
        result = profiler.recommend_pruning(
            np.array([]),
            target_efficiency=0.01,
            current_accuracy=0.8,
        )
        assert result["n_total"] == 0


class TestInputValidation:
    def test_temperature_positive(self):
        with pytest.raises(ValueError):
            LandauerInferenceProfiler(T=0.0)

    def test_gpu_energy_positive(self):
        with pytest.raises(ValueError):
            LandauerInferenceProfiler(gpu_energy_per_op=0.0)

    def test_negative_params_raises(self, profiler):
        with pytest.raises(ValueError):
            profiler.entropy_per_step(-1)
