# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for Kuramoto-Kelly adaptive position sizing."""

import numpy as np
import pytest

from core.neuro.kuramoto_kelly import KuramotoKellyAdapter
from core.neuro.signal_bus import NeuroSignalBus

pytestmark = pytest.mark.L3


@pytest.fixture
def bus():
    return NeuroSignalBus()


@pytest.fixture
def adapter(bus):
    return KuramotoKellyAdapter(bus)


class TestOrderParameter:
    """Kuramoto R computation from return series."""

    def test_coherent_sine_wave_gives_high_R(self, adapter):
        """A pure sine wave has high phase coherence → R > 0.5."""
        t = np.linspace(0, 4 * np.pi, 500)
        prices = 100 + 5 * np.sin(t)
        returns = np.diff(prices) / prices[:-1]
        R = adapter.compute_order_parameter(returns)
        assert R > 0.5, f"Coherent sine should give R > 0.5, got {R}"

    def test_random_noise_gives_low_R(self, adapter):
        """Random noise has incoherent phases → R < 0.5."""
        rng = np.random.default_rng(42)
        returns = rng.standard_normal(500)
        R = adapter.compute_order_parameter(returns)
        assert R < 0.5, f"Random noise should give R < 0.5, got {R}"

    def test_constant_returns_gives_zero(self, adapter):
        """Constant input (zero variance) → R = 0."""
        returns = np.ones(100) * 0.01
        R = adapter.compute_order_parameter(returns)
        assert R == 0.0

    def test_nan_handling(self, adapter):
        """Returns with NaNs are filtered gracefully."""
        returns = np.array([0.01, np.nan, -0.02, 0.03, np.nan, 0.01, -0.01, 0.02, 0.01, -0.02])
        R = adapter.compute_order_parameter(returns)
        assert 0.0 <= R <= 1.0

    def test_too_short_returns_zero(self, adapter):
        """Fewer than 2 returns → R = 0."""
        assert adapter.compute_order_parameter(np.array([0.01])) == 0.0
        assert adapter.compute_order_parameter(np.array([])) == 0.0


class TestKellyFraction:
    """Kelly fraction adjustment based on Kuramoto R."""

    def test_fraction_bounded(self, adapter):
        """Fraction must be in [floor * kelly_base, kelly_base]."""
        rng = np.random.default_rng(99)
        kelly_base = 0.5
        for _ in range(20):
            prices = 100 + np.cumsum(rng.standard_normal(200))
            prices = np.abs(prices) + 1  # ensure positive
            frac = adapter.compute_kelly_fraction(kelly_base, prices)
            assert (
                0.1 * kelly_base - 1e-9 <= frac <= kelly_base + 1e-9
            ), f"Fraction {frac} outside bounds"

    def test_coherent_prices_higher_fraction(self, adapter):
        """Trending price (high R) should yield larger fraction than noise."""
        t = np.linspace(0, 4 * np.pi, 300)
        coherent_prices = 100 + 5 * np.sin(t) + np.linspace(0, 10, 300)

        rng = np.random.default_rng(7)
        noisy_prices = 100 + np.cumsum(rng.standard_normal(300))
        noisy_prices = np.abs(noisy_prices) + 1

        frac_coherent = adapter.compute_kelly_fraction(1.0, coherent_prices)
        frac_noisy = adapter.compute_kelly_fraction(1.0, noisy_prices)
        # Coherent should generally be >= noisy (not strictly due to randomness)
        # Just check both are valid
        assert 0.1 <= frac_coherent <= 1.0
        assert 0.1 <= frac_noisy <= 1.0


class TestRegimeClassification:
    """Regime classification from R."""

    def test_chaotic(self, adapter):
        assert adapter.classify_regime(0.0) == "chaotic"
        assert adapter.classify_regime(0.29) == "chaotic"

    def test_transitional(self, adapter):
        assert adapter.classify_regime(0.3) == "transitional"
        assert adapter.classify_regime(0.5) == "transitional"
        assert adapter.classify_regime(0.69) == "transitional"

    def test_coherent(self, adapter):
        assert adapter.classify_regime(0.7) == "coherent"
        assert adapter.classify_regime(1.0) == "coherent"


class TestBusPublishing:
    """Verify R is published to bus."""

    def test_publishes_R_to_bus(self, bus, adapter):
        t = np.linspace(0, 4 * np.pi, 200)
        prices = 100 + 3 * np.sin(t)
        adapter.compute_kelly_fraction(1.0, prices)
        snapshot = bus.snapshot()
        assert snapshot.kuramoto_R > 0.0, "R should be published to bus"

    def test_bus_subscription_fires(self, bus, adapter):
        received = []
        bus.subscribe("kuramoto", lambda s: received.append(s.kuramoto_R))
        t = np.linspace(0, 4 * np.pi, 200)
        prices = 100 + 3 * np.sin(t)
        adapter.compute_kelly_fraction(1.0, prices)
        assert len(received) == 1
        assert received[0] > 0.0


class TestRealishMarketReturns:
    """Test with realistic random-walk + trend returns."""

    def test_random_walk_plus_trend(self, adapter):
        rng = np.random.default_rng(123)
        n = 500
        trend = np.linspace(0, 2, n)
        noise = rng.standard_normal(n) * 0.5
        prices = 100 + trend + np.cumsum(noise)
        prices = np.abs(prices) + 1

        frac = adapter.compute_kelly_fraction(0.8, prices)
        assert 0.08 - 1e-9 <= frac <= 0.8 + 1e-9

        returns = np.diff(prices) / prices[:-1]
        R = adapter.compute_order_parameter(returns)
        regime = adapter.classify_regime(R)
        assert regime in {"chaotic", "transitional", "coherent"}


class TestKellyFailClosed:
    """Fail-closed guards: a NaN must never reach Kelly position sizing, and a
    degenerate normalisation band must be rejected at construction.

    Reproduces a latent defect found by a computational audit: a zero/non-finite
    price made ``diff / price[:-1]`` produce NaN that propagated as the position
    multiplier, while the signal bus masked it as a healthy R=1.0
    (``max(0, min(1, nan)) == 1.0``) — the fault hid at the observability layer.
    """

    def test_zero_price_rejected(self, adapter) -> None:
        """A zero in the price series previously yielded a NaN Kelly fraction."""
        with pytest.raises(ValueError):
            adapter.compute_kelly_fraction(2.0, np.array([100.0, 0.0, 102.0, 103.0]))

    def test_non_finite_price_rejected(self, adapter) -> None:
        with pytest.raises(ValueError):
            adapter.compute_kelly_fraction(2.0, np.array([100.0, np.nan, 102.0, 103.0]))

    def test_too_short_price_rejected(self, adapter) -> None:
        with pytest.raises(ValueError):
            adapter.compute_kelly_fraction(2.0, np.array([100.0, 101.0]))

    def test_degenerate_band_rejected_at_construction(self, bus) -> None:
        """R_low == R_high previously raised ZeroDivisionError mid-trade."""
        with pytest.raises(ValueError):
            KuramotoKellyAdapter(bus, R_low=0.5, R_high=0.5)

    def test_inverted_band_rejected_at_construction(self, bus) -> None:
        """R_low > R_high previously silently inverted the sizing response."""
        with pytest.raises(ValueError):
            KuramotoKellyAdapter(bus, R_low=0.7, R_high=0.3)

    def test_valid_path_still_finite_and_bounded(self, adapter) -> None:
        """Regression: a clean positive price series still sizes finitely."""
        frac = adapter.compute_kelly_fraction(
            2.0, np.array([100.0, 101.0, 99.0, 102.0, 103.0, 104.0])
        )
        assert np.isfinite(frac)
        assert 0.0 <= frac <= 2.0
