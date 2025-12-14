# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Additional property-based tests for entropy and phase analysis.

These tests complement existing property tests with more coverage of edge
cases and mathematical properties.
"""
from __future__ import annotations

import numpy as np
import pytest

try:
    from hypothesis import assume, given, settings
    from hypothesis import strategies as st
    from hypothesis.extra.numpy import arrays
except ImportError:  # pragma: no cover
    pytest.skip("hypothesis not installed", allow_module_level=True)

from core.indicators.entropy import delta_entropy, entropy
from core.indicators.kuramoto import (
    compute_phase,
    kuramoto_order,
    multi_asset_kuramoto,
)


@st.composite
def valid_returns(draw, min_length=20, max_length=500):
    """Generate valid return sequences for entropy testing."""
    length = draw(st.integers(min_value=min_length, max_value=max_length))
    return draw(
        arrays(
            dtype=np.float64,
            shape=length,
            elements=st.floats(
                min_value=-0.2,
                max_value=0.2,
                allow_nan=False,
                allow_infinity=False,
            ),
        )
    )


class TestEntropyAdditionalProperties:
    """Additional property-based tests for entropy functions."""

    @given(st.integers(min_value=50, max_value=200))
    @settings(deadline=None, max_examples=20)
    def test_entropy_with_larger_samples(self, n):
        """With larger samples, entropy properties should be more stable."""
        np.random.seed(42)
        # Highly ordered signal
        ordered = np.sort(np.random.normal(0, 1, n))
        # Random signal
        random = np.random.normal(0, 1, n)

        H_ordered = entropy(ordered, bins=30)
        H_random = entropy(random, bins=30)

        # Both should be positive
        assert H_ordered >= 0.0
        assert H_random >= 0.0

    @given(valid_returns(min_length=200, max_length=500))
    @settings(deadline=None, max_examples=30)
    def test_delta_entropy_finite(self, returns):
        """Delta entropy should always be finite."""
        assume(len(returns) >= 200)
        dH = delta_entropy(returns, window=100)
        assert np.isfinite(dH)

    @given(st.integers(min_value=5, max_value=100))
    @settings(deadline=None, max_examples=30)
    def test_entropy_scale_invariance(self, n):
        """Entropy should be scale-invariant (after normalization)."""
        np.random.seed(42)
        data = np.random.normal(0, 1, n + 10)  # Add padding

        # Same distribution, different scales
        H1 = entropy(data, bins=20)
        H2 = entropy(data * 10, bins=20)
        H3 = entropy(data * 100, bins=20)

        # Should be similar (entropy is computed on normalized data)
        assert np.isclose(H1, H2, rtol=0.1)
        assert np.isclose(H1, H3, rtol=0.1)

    @given(st.integers(min_value=10, max_value=100))
    @settings(deadline=None, max_examples=20)
    def test_entropy_float32_compatibility(self, n):
        """Float32 mode should produce similar results to float64."""
        np.random.seed(42)
        data = np.random.normal(0, 1, n + 10)

        H_64 = entropy(data, bins=20, use_float32=False)
        H_32 = entropy(data, bins=20, use_float32=True)

        # Should be very close despite precision difference
        assert np.isclose(H_64, H_32, rtol=0.01)


class TestPhaseAnalysisProperties:
    """Property-based tests for phase analysis functions."""

    @given(
        arrays(
            dtype=np.float64,
            shape=st.integers(min_value=10, max_value=200),
            elements=st.floats(
                min_value=-10.0,
                max_value=10.0,
                allow_nan=False,
                allow_infinity=False,
            ),
        )
    )
    @settings(deadline=None, max_examples=50)
    def test_compute_phase_preserves_length(self, signal):
        """Phase computation should preserve signal length."""
        phases = compute_phase(signal)
        assert len(phases) == len(signal)

    @given(st.integers(min_value=10, max_value=100))
    @settings(deadline=None, max_examples=30)
    def test_phase_of_sine_wave(self, n):
        """Phase of sine wave should follow expected pattern."""
        # Pure sine wave
        t = np.linspace(0, 2 * np.pi, n)
        signal = np.sin(t)
        phases = compute_phase(signal)

        # Phase should be well-defined and in valid range
        assert np.all(phases >= -np.pi)
        assert np.all(phases <= np.pi)
        # Phase should be roughly monotonic (with wrapping)
        # Just verify basic sanity
        assert np.all(np.isfinite(phases))

    @given(
        st.integers(min_value=2, max_value=20),  # num series
        st.integers(min_value=20, max_value=100),  # length
    )
    @settings(deadline=None, max_examples=20)
    def test_multi_asset_kuramoto_properties(self, n_assets, length):
        """Multi-asset Kuramoto should satisfy basic properties."""
        np.random.seed(42)
        # Generate random price series
        series_list = [
            100 * np.exp(np.cumsum(np.random.normal(0, 0.01, length)))
            for _ in range(n_assets)
        ]

        # Should complete successfully
        sync = multi_asset_kuramoto(series_list)
        assert 0.0 <= sync <= 1.0
        assert np.isfinite(sync)


class TestRobustnessProperties:
    """Property tests for robustness to edge cases."""

    @given(st.integers(min_value=2, max_value=10))
    @settings(deadline=None, max_examples=20)
    def test_minimum_length_signals(self, n):
        """Indicators should handle minimum length signals gracefully."""
        signal = np.array([1.0] * n)

        # Should not crash
        phases = compute_phase(signal)
        assert len(phases) == n

        order = kuramoto_order(phases)
        assert 0.0 <= order <= 1.0

        H = entropy(signal, bins=min(5, n))
        assert H >= 0.0

    @given(
        arrays(
            dtype=np.float64,
            shape=st.integers(min_value=20, max_value=100),
            elements=st.floats(
                min_value=-1e6,
                max_value=1e6,
                allow_nan=False,
                allow_infinity=False,
            ),
        )
    )
    @settings(deadline=None, max_examples=30)
    def test_large_magnitude_values(self, signal):
        """Indicators should handle large magnitude values."""
        # Should complete without overflow
        phases = compute_phase(signal)
        assert np.all(np.isfinite(phases))

        order = kuramoto_order(phases)
        assert np.isfinite(order)
        assert 0.0 <= order <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])
