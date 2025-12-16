# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for coherence and safety metrics numerical contracts.

These tests verify the numerical correctness of coherence metrics:
- Output bounds [0, 1] for all metrics
- Finite outputs for zero vectors
- Finite outputs for empty inputs
- Proper handling of NaN/Inf in strict/non-strict modes
"""

from __future__ import annotations

import numpy as np
import pytest

try:
    from tradepulse.sdk.mlsdm.utils.coherence_safety_metrics import (
        CoherenceMetrics,
        compute_all_metrics,
        cosine_coherence,
        memory_coherence,
        safety_score,
        temporal_coherence,
    )
    from tradepulse.sdk.mlsdm.utils.input_validator import NumericalContractError
except ImportError:
    from src.tradepulse.sdk.mlsdm.utils.coherence_safety_metrics import (
        CoherenceMetrics,
        compute_all_metrics,
        cosine_coherence,
        memory_coherence,
        safety_score,
        temporal_coherence,
    )
    from src.tradepulse.sdk.mlsdm.utils.input_validator import NumericalContractError


class TestCosineCoherence:
    """Tests for cosine_coherence function."""

    def test_identical_vectors_return_1(self) -> None:
        """Identical vectors have maximum coherence of 1.0."""
        vec = np.array([1.0, 2.0, 3.0])
        result = cosine_coherence(vec, vec)
        assert result == pytest.approx(1.0)

    def test_opposite_vectors_return_0(self) -> None:
        """Opposite vectors have minimum coherence of 0.0."""
        vec_a = np.array([1.0, 0.0, 0.0])
        vec_b = np.array([-1.0, 0.0, 0.0])
        result = cosine_coherence(vec_a, vec_b)
        assert result == pytest.approx(0.0)

    def test_orthogonal_vectors_return_05(self) -> None:
        """Orthogonal vectors have neutral coherence of 0.5."""
        vec_a = np.array([1.0, 0.0])
        vec_b = np.array([0.0, 1.0])
        result = cosine_coherence(vec_a, vec_b)
        assert result == pytest.approx(0.5)

    def test_zero_vector_returns_05(self) -> None:
        """Zero vector comparison returns neutral coherence 0.5."""
        vec_a = np.zeros(4)
        vec_b = np.array([1.0, 2.0, 3.0, 4.0])
        result = cosine_coherence(vec_a, vec_b)
        assert result == pytest.approx(0.5)

    def test_both_zero_vectors_return_05(self) -> None:
        """Both zero vectors return neutral coherence 0.5."""
        vec_a = np.zeros(4)
        vec_b = np.zeros(4)
        result = cosine_coherence(vec_a, vec_b)
        assert result == pytest.approx(0.5)

    def test_output_always_in_bounds(self) -> None:
        """Output is always in [0, 1] range."""
        rng = np.random.default_rng(42)
        for _ in range(100):
            vec_a = rng.standard_normal(10)
            vec_b = rng.standard_normal(10)
            result = cosine_coherence(vec_a, vec_b)
            assert 0.0 <= result <= 1.0

    def test_rejects_nan_strict_mode(self) -> None:
        """Rejects NaN in strict mode."""
        vec_a = np.array([1.0, np.nan])
        vec_b = np.array([1.0, 2.0])
        with pytest.raises(NumericalContractError):
            cosine_coherence(vec_a, vec_b, strict_mode=True)

    def test_rejects_inf_strict_mode(self) -> None:
        """Rejects Inf in strict mode."""
        vec_a = np.array([1.0, np.inf])
        vec_b = np.array([1.0, 2.0])
        with pytest.raises(NumericalContractError):
            cosine_coherence(vec_a, vec_b, strict_mode=True)

    def test_sanitizes_nan_non_strict_mode(self) -> None:
        """Sanitizes NaN in non-strict mode and returns finite."""
        vec_a = np.array([1.0, np.nan])
        vec_b = np.array([1.0, 2.0])
        result = cosine_coherence(vec_a, vec_b, strict_mode=False)
        assert np.isfinite(result)
        assert 0.0 <= result <= 1.0

    def test_shape_mismatch_raises(self) -> None:
        """Shape mismatch raises ValueError."""
        vec_a = np.array([1.0, 2.0])
        vec_b = np.array([1.0, 2.0, 3.0])
        with pytest.raises(ValueError, match="Shape mismatch"):
            cosine_coherence(vec_a, vec_b)


class TestTemporalCoherence:
    """Tests for temporal_coherence function."""

    def test_empty_window_returns_1(self) -> None:
        """Empty window returns maximum coherence 1.0."""
        result = temporal_coherence([])
        assert result == pytest.approx(1.0)

    def test_single_vector_returns_1(self) -> None:
        """Single vector window returns maximum coherence 1.0."""
        vec = np.array([1.0, 2.0, 3.0])
        result = temporal_coherence([vec])
        assert result == pytest.approx(1.0)

    def test_identical_vectors_return_1(self) -> None:
        """Window of identical vectors returns 1.0."""
        vec = np.array([1.0, 2.0, 3.0])
        result = temporal_coherence([vec, vec, vec, vec])
        assert result == pytest.approx(1.0)

    def test_opposite_vectors_return_0(self) -> None:
        """Window with opposite consecutive vectors returns 0.0."""
        vec_a = np.array([1.0, 0.0])
        vec_b = np.array([-1.0, 0.0])
        result = temporal_coherence([vec_a, vec_b])
        assert result == pytest.approx(0.0)

    def test_output_always_in_bounds(self) -> None:
        """Output is always in [0, 1]."""
        rng = np.random.default_rng(42)
        window = [rng.standard_normal(5) for _ in range(10)]
        result = temporal_coherence(window)
        assert 0.0 <= result <= 1.0

    def test_finite_for_zero_vectors(self) -> None:
        """Returns finite for window with zero vectors."""
        window = [np.zeros(4), np.zeros(4), np.array([1.0, 2.0, 3.0, 4.0])]
        result = temporal_coherence(window)
        assert np.isfinite(result)
        assert 0.0 <= result <= 1.0


class TestMemoryCoherence:
    """Tests for memory_coherence function."""

    def test_identical_levels_return_1(self) -> None:
        """Identical memory levels return 1.0."""
        vec = np.array([1.0, 2.0, 3.0])
        result = memory_coherence(vec, vec, vec)
        assert result == pytest.approx(1.0)

    def test_zero_vectors_return_finite(self) -> None:
        """Zero memory levels return finite value."""
        zero = np.zeros(4)
        result = memory_coherence(zero, zero, zero)
        assert np.isfinite(result)
        assert 0.0 <= result <= 1.0

    def test_output_always_in_bounds(self) -> None:
        """Output is always in [0, 1]."""
        rng = np.random.default_rng(42)
        for _ in range(50):
            l1 = rng.standard_normal(8)
            l2 = rng.standard_normal(8)
            l3 = rng.standard_normal(8)
            result = memory_coherence(l1, l2, l3)
            assert 0.0 <= result <= 1.0

    def test_custom_weights(self) -> None:
        """Custom weights are applied correctly."""
        l1 = np.array([1.0, 0.0])
        l2 = np.array([-1.0, 0.0])  # Opposite to L1
        l3 = np.array([1.0, 0.0])  # Same as L1

        # With weight only on L1-L2 (opposite), coherence should be low
        result_12_only = memory_coherence(l1, l2, l3, weights=(1.0, 0.0, 0.0))
        assert result_12_only == pytest.approx(0.0)

        # With weight only on L1-L3 (same), coherence should be high
        result_13_only = memory_coherence(l1, l2, l3, weights=(0.0, 0.0, 1.0))
        assert result_13_only == pytest.approx(1.0)


class TestSafetyScore:
    """Tests for safety_score function."""

    def test_zero_vector_returns_1(self) -> None:
        """Zero deviation from zero reference returns 1.0."""
        result = safety_score(np.zeros(4))
        assert result == pytest.approx(1.0)

    def test_max_deviation_returns_0(self) -> None:
        """Maximum deviation returns 0.0."""
        result = safety_score(np.array([10.0, 0.0, 0.0]), max_deviation=10.0)
        assert result == pytest.approx(0.0)

    def test_half_deviation_returns_05(self) -> None:
        """Half of max deviation returns 0.5."""
        result = safety_score(np.array([5.0, 0.0, 0.0]), max_deviation=10.0)
        assert result == pytest.approx(0.5)

    def test_output_always_in_bounds(self) -> None:
        """Output is always in [0, 1]."""
        rng = np.random.default_rng(42)
        for _ in range(100):
            current = rng.standard_normal(5) * 100
            result = safety_score(current)
            assert 0.0 <= result <= 1.0

    def test_with_reference(self) -> None:
        """Works correctly with custom reference."""
        current = np.array([10.0, 0.0])
        reference = np.array([10.0, 0.0])  # Same as current
        result = safety_score(current, reference)
        assert result == pytest.approx(1.0)  # No deviation

    def test_finite_for_nan_non_strict(self) -> None:
        """Returns finite for NaN input in non-strict mode."""
        current = np.array([1.0, np.nan, 2.0])
        result = safety_score(current, strict_mode=False)
        assert np.isfinite(result)
        assert 0.0 <= result <= 1.0


class TestComputeAllMetrics:
    """Tests for compute_all_metrics function."""

    def test_returns_coherence_metrics(self) -> None:
        """Returns CoherenceMetrics dataclass."""
        current = np.array([1.0, 2.0, 3.0])
        result = compute_all_metrics(current)
        assert isinstance(result, CoherenceMetrics)

    def test_all_values_in_bounds(self) -> None:
        """All metric values are in [0, 1]."""
        rng = np.random.default_rng(42)
        current = rng.standard_normal(10)
        reference = rng.standard_normal(10)
        window = [rng.standard_normal(10) for _ in range(5)]
        levels = (rng.standard_normal(10), rng.standard_normal(10), rng.standard_normal(10))

        result = compute_all_metrics(
            current,
            reference=reference,
            window=window,
            memory_levels=levels,
        )

        assert 0.0 <= result.cosine <= 1.0
        assert 0.0 <= result.temporal <= 1.0
        assert 0.0 <= result.memory <= 1.0
        assert 0.0 <= result.safety <= 1.0

    def test_to_dict(self) -> None:
        """to_dict returns proper dictionary."""
        current = np.array([1.0, 2.0, 3.0])
        result = compute_all_metrics(current)
        d = result.to_dict()

        assert isinstance(d, dict)
        assert "cosine" in d
        assert "temporal" in d
        assert "memory" in d
        assert "safety" in d

    def test_handles_none_inputs(self) -> None:
        """Handles None optional inputs gracefully."""
        current = np.array([1.0, 2.0, 3.0])
        result = compute_all_metrics(
            current,
            reference=None,
            window=None,
            memory_levels=None,
        )

        # All values should be finite and in bounds
        assert np.isfinite(result.cosine)
        assert np.isfinite(result.temporal)
        assert np.isfinite(result.memory)
        assert np.isfinite(result.safety)


class TestCoherenceMetricsOutputBounds:
    """Comprehensive tests for output bounds [0, 1]."""

    @pytest.mark.parametrize("seed", range(10))
    def test_cosine_coherence_bounds_random(self, seed: int) -> None:
        """Cosine coherence always in [0, 1] for random inputs."""
        rng = np.random.default_rng(seed)
        vec_a = rng.standard_normal(20)
        vec_b = rng.standard_normal(20)
        result = cosine_coherence(vec_a, vec_b)
        assert 0.0 <= result <= 1.0

    @pytest.mark.parametrize("size", [1, 2, 10, 100, 1000])
    def test_cosine_coherence_various_sizes(self, size: int) -> None:
        """Cosine coherence works for various vector sizes."""
        rng = np.random.default_rng(42)
        vec_a = rng.standard_normal(size)
        vec_b = rng.standard_normal(size)
        result = cosine_coherence(vec_a, vec_b)
        assert 0.0 <= result <= 1.0
        assert np.isfinite(result)
