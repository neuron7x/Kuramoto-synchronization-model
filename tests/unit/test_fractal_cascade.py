"""Tests for fractal cascade utilities including Hölder field estimation."""

from __future__ import annotations

import numpy as np
import pytest

from utils.fractal_cascade import DyadicPMCascade, pink_noise

try:
    import pywt  # noqa: F401

    _PYWT_AVAILABLE = True
except ImportError:
    _PYWT_AVAILABLE = False


class TestDyadicPMCascade:
    """Tests for the DyadicPMCascade class."""

    def test_cascade_sample_basic(self):
        """Test basic cascade sampling."""
        cascade = DyadicPMCascade(depth=8, p=0.6)
        samples = cascade.sample(64)
        assert len(samples) == 64
        assert all(s > 0 for s in samples)

    def test_cascade_sample_reproducible(self):
        """Test that cascade is reproducible with same RNG."""
        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(42)

        cascade1 = DyadicPMCascade(depth=8, p=0.6, rng=rng1)
        cascade2 = DyadicPMCascade(depth=8, p=0.6, rng=rng2)

        samples1 = cascade1.sample(32)
        samples2 = cascade2.sample(32)

        np.testing.assert_array_equal(samples1, samples2)

    def test_cascade_adjust_heavy_tail(self):
        """Test heavy tail adjustment."""
        cascade = DyadicPMCascade(depth=8, p=0.6, heavy_tail=0.5)

        cascade.adjust_heavy_tail(0.3)
        assert cascade.heavy_tail == pytest.approx(0.8)

        cascade.adjust_heavy_tail(0.5)  # Should clamp to 1.0
        assert cascade.heavy_tail == pytest.approx(1.0)

        cascade.adjust_heavy_tail(-1.5)  # Should clamp to 0.0
        assert cascade.heavy_tail == pytest.approx(0.0)

    @pytest.mark.skipif(not _PYWT_AVAILABLE, reason="PyWavelets not installed")
    def test_cascade_holder_field(self):
        """Test Hölder field estimation from cascade."""
        rng = np.random.default_rng(42)
        cascade = DyadicPMCascade(depth=10, p=0.6, rng=rng)

        positions, h_values = cascade.holder_field(n=100)

        assert len(positions) == len(h_values)
        assert len(positions) > 0
        # Hölder values should be in reasonable range
        assert all(0.0 <= h <= 2.0 for h in h_values)

    def test_cascade_theoretical_holder(self):
        """Test theoretical Hölder exponent computation."""
        # With p=0.5 (symmetric), h should be log(2)/log(2) = 1
        cascade_sym = DyadicPMCascade(depth=8, p=0.5)
        h_sym = cascade_sym.theoretical_holder()
        assert h_sym == pytest.approx(1.0)

        # With p closer to 0 or 1, h should be smaller
        cascade_asym = DyadicPMCascade(depth=8, p=0.9)
        h_asym = cascade_asym.theoretical_holder()
        assert h_asym < 1.0

    def test_cascade_invalid_params(self):
        """Test error handling for invalid parameters."""
        with pytest.raises(ValueError, match="p must be in"):
            DyadicPMCascade(depth=8, p=1.5)

        with pytest.raises(ValueError, match="p must be in"):
            DyadicPMCascade(depth=8, p=-0.1)

        with pytest.raises(ValueError, match="depth must be positive"):
            DyadicPMCascade(depth=0, p=0.6)

        with pytest.raises(ValueError, match="heavy_tail must be within"):
            DyadicPMCascade(depth=8, p=0.6, heavy_tail=1.5)


class TestPinkNoise:
    """Tests for the pink noise generator."""

    def test_pink_noise_basic(self):
        """Test basic pink noise generation."""
        noise = pink_noise(1024, beta=1.0)
        assert len(noise) == 1024
        # Should be normalized
        assert np.abs(np.mean(noise)) < 0.1
        assert 0.8 < np.std(noise) < 1.2

    def test_pink_noise_reproducible(self):
        """Test that pink noise is reproducible with same RNG."""
        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(42)

        noise1 = pink_noise(256, beta=1.0, rng=rng1)
        noise2 = pink_noise(256, beta=1.0, rng=rng2)

        np.testing.assert_array_almost_equal(noise1, noise2)

    def test_pink_noise_different_betas(self):
        """Test pink noise with different spectral exponents."""
        rng = np.random.default_rng(42)

        # White noise (beta=0)
        white = pink_noise(1024, beta=0.0, rng=rng)
        assert len(white) == 1024

        # Brown noise (beta=2)
        brown = pink_noise(1024, beta=2.0, rng=rng)
        assert len(brown) == 1024

    def test_pink_noise_invalid_n(self):
        """Test error handling for invalid n."""
        with pytest.raises(ValueError, match="n must be positive"):
            pink_noise(0)

        with pytest.raises(ValueError, match="n must be positive"):
            pink_noise(-10)
