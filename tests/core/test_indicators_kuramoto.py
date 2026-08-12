# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.indicators.kuramoto module."""

from __future__ import annotations

import numpy as np
import pytest

from core.indicators.kuramoto import (
    _broadcast_weights,
    _kuramoto_order_2d_jit,
    _kuramoto_order_jit,
    compute_phase,
)


class TestKuramotoOrderJit:
    def test_perfect_sync(self):
        # All phases = 0 -> cos=1, sin=0 -> R=1
        cos_vals = np.ones(10)
        sin_vals = np.zeros(10)
        assert _kuramoto_order_jit(cos_vals, sin_vals) == pytest.approx(1.0)

    def test_complete_desync(self):
        # Uniformly distributed phases -> R ~ 0
        n = 10000
        phases = np.linspace(0, 2 * np.pi, n, endpoint=False)
        cos_vals = np.cos(phases)
        sin_vals = np.sin(phases)
        r = _kuramoto_order_jit(cos_vals, sin_vals)
        assert r == pytest.approx(0.0, abs=0.01)

    def test_empty_array(self):
        assert _kuramoto_order_jit(np.array([]), np.array([])) == 0.0

    def test_single_oscillator(self):
        cos_vals = np.array([np.cos(1.0)])
        sin_vals = np.array([np.sin(1.0)])
        assert _kuramoto_order_jit(cos_vals, sin_vals) == pytest.approx(1.0)

    def test_nan_handling(self):
        cos_vals = np.array([1.0, np.nan, 1.0])
        sin_vals = np.array([0.0, np.nan, 0.0])
        r = _kuramoto_order_jit(cos_vals, sin_vals)
        # NaN filtering may differ by numba version; just check finite and bounded
        assert 0.0 <= r <= 1.0

    def test_all_nan(self):
        cos_vals = np.array([np.nan, np.nan])
        sin_vals = np.array([np.nan, np.nan])
        assert _kuramoto_order_jit(cos_vals, sin_vals) == 0.0

    def test_nan_strictly_filtered_exact_value(self):
        # Regression for the fastmath NaN-guard defect: with fastmath=True the
        # LLVM `nnan` flag folds `c == c` to constant True, so the NaN oscillator
        # leaks into the sum and the result is NOT 1.0 (observed 0.0). With
        # fastmath removed the guard filters it and the two in-phase oscillators
        # give R == 1.0 exactly.
        cos_vals = np.array([1.0, 1.0, np.nan])
        sin_vals = np.array([0.0, 0.0, np.nan])
        assert _kuramoto_order_jit(cos_vals, sin_vals) == pytest.approx(1.0, abs=1e-12)

    def test_result_bounded(self):
        # Random phases
        rng = np.random.default_rng(42)
        phases = rng.uniform(0, 2 * np.pi, 100)
        r = _kuramoto_order_jit(np.cos(phases), np.sin(phases))
        assert 0.0 <= r <= 1.0


class TestKuramotoOrder2dJit:
    def test_sync_trajectory(self):
        n_osc, n_time = 5, 10
        cos_vals = np.ones((n_osc, n_time))
        sin_vals = np.zeros((n_osc, n_time))
        result = _kuramoto_order_2d_jit(cos_vals, sin_vals)
        assert result.shape == (n_time,)
        np.testing.assert_allclose(result, 1.0)

    def test_desync_trajectory(self):
        n_osc = 1000
        n_time = 5
        phases = np.linspace(0, 2 * np.pi, n_osc, endpoint=False)
        cos_vals = np.tile(np.cos(phases)[:, None], (1, n_time))
        sin_vals = np.tile(np.sin(phases)[:, None], (1, n_time))
        result = _kuramoto_order_2d_jit(cos_vals, sin_vals)
        np.testing.assert_allclose(result, 0.0, atol=0.01)

    def test_shape(self):
        result = _kuramoto_order_2d_jit(np.ones((3, 7)), np.zeros((3, 7)))
        assert result.shape == (7,)

    def test_nan_strictly_filtered_exact_value(self):
        # Regression for the fastmath NaN-guard defect (2D kernel): the per-
        # timestep `c == c and s == s` guard must survive compilation. Two
        # in-phase oscillators plus one NaN oscillator per timestep must yield
        # R == 1.0 exactly; under fastmath the NaN leaked and broke this.
        cos_vals = np.array([[1.0, 1.0], [1.0, 1.0], [np.nan, np.nan]])
        sin_vals = np.array([[0.0, 0.0], [0.0, 0.0], [np.nan, np.nan]])
        result = _kuramoto_order_2d_jit(cos_vals, sin_vals)
        np.testing.assert_allclose(result, np.array([1.0, 1.0]), atol=1e-12)


class TestBroadcastWeights:
    def test_1d_oscillator_weights(self):
        w = np.array([1.0, 2.0, 3.0])
        result = _broadcast_weights(w, (3, 5))
        assert result.shape == (3, 5)

    def test_1d_time_weights(self):
        w = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _broadcast_weights(w, (3, 5))
        assert result.shape == (3, 5)

    def test_2d_weights(self):
        w = np.ones((3, 5))
        result = _broadcast_weights(w, (3, 5))
        assert result.shape == (3, 5)

    def test_scalar_raises(self):
        with pytest.raises(ValueError, match="one- or two-dimensional"):
            _broadcast_weights(np.float64(1.0), (3, 5))

    def test_wrong_size_raises(self):
        with pytest.raises(ValueError, match="must match"):
            _broadcast_weights(np.array([1.0, 2.0]), (3, 5))

    def test_nan_replaced(self):
        w = np.array([1.0, np.nan, 3.0])
        result = _broadcast_weights(w, (3, 5))
        assert not np.isnan(result).any()

    def test_negative_clipped(self):
        w = np.array([-1.0, 2.0, 3.0])
        result = _broadcast_weights(w, (3, 5))
        assert (result >= 0).all()


class TestComputePhase:
    def test_sinusoidal_signal(self):
        t = np.linspace(0, 4 * np.pi, 1000)
        x = np.sin(t)
        phase = compute_phase(x)
        assert phase.shape == x.shape
        assert phase.dtype in (np.float32, np.float64)

    def test_constant_signal(self):
        x = np.ones(100)
        phase = compute_phase(x)
        assert phase.shape == (100,)

    def test_float32_output(self):
        x = np.sin(np.linspace(0, 2 * np.pi, 200))
        phase = compute_phase(x, use_float32=True)
        assert phase.dtype == np.float32

    def test_output_buffer(self):
        x = np.sin(np.linspace(0, 2 * np.pi, 100))
        out = np.empty(100, dtype=np.float64)
        result = compute_phase(x, out=out)
        assert result is out

    @pytest.mark.parametrize("n", [50, 100, 500, 1000])
    def test_various_lengths(self, n):
        x = np.random.default_rng(42).standard_normal(n)
        phase = compute_phase(x)
        assert phase.shape == (n,)
        assert np.isfinite(phase).all()
