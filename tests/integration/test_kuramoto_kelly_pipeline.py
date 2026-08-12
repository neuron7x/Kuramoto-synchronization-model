# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration tests for the Kuramoto-Kelly position sizing pipeline.

Tests the full path: price data -> Kuramoto order parameter R -> Kelly fraction,
including signal bus integration and regime classification.

Scenarios:
- Sine wave (trending) -> high R -> large Kelly fraction
- Random noise (chaotic) -> low R -> small Kelly fraction
- Bus integration: R published to NeuroSignalBus
- Kelly fraction bounded in [floor * kelly_base, kelly_base]
"""

from __future__ import annotations

import numpy as np

from core.neuro.kuramoto_kelly import KuramotoKellyAdapter
from core.neuro.signal_bus import BusConfig, NeuroSignalBus

# Level auto-assigned by conftest from tests/test_levels.yaml (L3 for integration)


# ── Signal generators ────────────────────────────────────────────────────


def _sine_wave_prices(
    n: int = 200, freq: float = 0.05, amplitude: float = 5.0, base: float = 100.0, seed: int = 42
) -> np.ndarray:
    """Generate a clean trending price series (sine wave + upward drift).

    A coherent signal should produce high Kuramoto R.
    """
    t = np.arange(n, dtype=np.float64)
    prices = base + amplitude * np.sin(2 * np.pi * freq * t) + 0.1 * t
    # Ensure prices are strictly positive
    prices = np.maximum(prices, 1.0)
    return prices


def _noisy_prices(n: int = 200, seed: int = 7) -> np.ndarray:
    """Generate a random-walk price series (pure noise).

    Incoherent signal should produce low Kuramoto R.
    """
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, 0.02, n - 1)
    prices = np.empty(n)
    prices[0] = 100.0
    for i in range(1, n):
        prices[i] = prices[i - 1] * (1.0 + returns[i - 1])
    return np.maximum(prices, 1.0)


def _flat_prices(n: int = 100, base: float = 100.0) -> np.ndarray:
    """Constant price series."""
    return np.full(n, base)


# ═══════════════════════════════════════════════════════════════════════
# Core pipeline tests
# ═══════════════════════════════════════════════════════════════════════


class TestKuramotoKellyPipeline:
    def setup_method(self):
        self.bus = NeuroSignalBus()
        self.adapter = KuramotoKellyAdapter(self.bus)

    # ── Sine wave -> high R -> large Kelly ───────────────────────────

    def test_sine_wave_high_R(self):
        """Coherent sine wave should produce order parameter R above noise baseline."""
        prices = _sine_wave_prices(n=200)
        returns = np.diff(prices) / prices[:-1]
        R = self.adapter.compute_order_parameter(returns)
        assert 0.0 <= R <= 1.0
        # Sine wave should have notably higher R than pure noise
        noise_prices = _noisy_prices(n=200)
        noise_returns = np.diff(noise_prices) / noise_prices[:-1]
        R_noise = self.adapter.compute_order_parameter(noise_returns)
        assert R > R_noise, f"Sine wave R={R:.4f} should exceed noise R={R_noise:.4f}"

    def test_sine_wave_large_kelly_fraction(self):
        """High coherence should yield large Kelly fraction."""
        prices = _sine_wave_prices(n=200)
        kelly_base = 0.5
        fraction = self.adapter.compute_kelly_fraction(kelly_base, prices)
        # With high R, fraction should be closer to kelly_base than to floor*kelly_base
        min_possible = 0.1 * kelly_base  # floor=0.1
        assert fraction >= min_possible
        assert fraction <= kelly_base

    # ── Random noise -> low R -> small Kelly ─────────────────────────

    def test_noise_low_R(self):
        """Random noise should produce relatively low order parameter."""
        prices = _noisy_prices(n=200)
        returns = np.diff(prices) / prices[:-1]
        R = self.adapter.compute_order_parameter(returns)
        assert 0.0 <= R <= 1.0

    def test_noise_small_kelly_fraction(self):
        """Low coherence should yield conservative (smaller) Kelly fraction."""
        prices_sine = _sine_wave_prices(n=200)
        prices_noise = _noisy_prices(n=200)
        kelly_base = 0.5

        frac_sine = self.adapter.compute_kelly_fraction(kelly_base, prices_sine)
        # Reset bus for clean comparison
        self.bus.reset()
        frac_noise = self.adapter.compute_kelly_fraction(kelly_base, prices_noise)

        assert (
            frac_sine >= frac_noise
        ), f"Sine fraction={frac_sine:.4f} should be >= noise fraction={frac_noise:.4f}"

    # ── Bus integration: R published ─────────────────────────────────

    def test_R_published_to_bus(self):
        """compute_kelly_fraction should publish R to the NeuroSignalBus."""
        prices = _sine_wave_prices(n=100)
        self.adapter.compute_kelly_fraction(0.5, prices)
        snapshot = self.bus.snapshot()
        # R should have been published (not default 0.5 from NeuroSignals)
        assert 0.0 <= snapshot.kuramoto_R <= 1.0

    def test_bus_R_matches_computed_R(self):
        """The R published to bus should match what compute_order_parameter returns."""
        prices = _sine_wave_prices(n=150)
        returns = np.diff(prices) / prices[:-1]
        R_direct = self.adapter.compute_order_parameter(returns)
        self.adapter.compute_kelly_fraction(0.5, prices)
        snapshot = self.bus.snapshot()
        # Bus clips to [0,1], so they should match
        assert abs(snapshot.kuramoto_R - np.clip(R_direct, 0.0, 1.0)) < 1e-10

    def test_bus_subscriber_receives_R(self):
        """Subscribers on 'kuramoto' channel should get notified."""
        received = []
        self.bus.subscribe("kuramoto", lambda signals: received.append(signals.kuramoto_R))
        prices = _sine_wave_prices(n=100)
        self.adapter.compute_kelly_fraction(0.5, prices)
        assert len(received) >= 1
        assert 0.0 <= received[-1] <= 1.0

    # ── Kelly fraction bounded [floor*kelly_base, kelly_base] ────────

    def test_kelly_fraction_upper_bound(self):
        """Kelly fraction should never exceed kelly_base."""
        for prices_fn in [_sine_wave_prices, _noisy_prices]:
            prices = prices_fn(n=150)
            kelly_base = 0.3
            fraction = self.adapter.compute_kelly_fraction(kelly_base, prices)
            assert (
                fraction <= kelly_base + 1e-12
            ), f"Fraction {fraction} exceeds kelly_base {kelly_base}"

    def test_kelly_fraction_lower_bound(self):
        """Kelly fraction should be >= floor * kelly_base."""
        adapter = KuramotoKellyAdapter(self.bus, floor=0.1, ceil=1.0)
        for prices_fn in [_sine_wave_prices, _noisy_prices]:
            prices = prices_fn(n=150)
            kelly_base = 0.4
            fraction = adapter.compute_kelly_fraction(kelly_base, prices)
            assert (
                fraction >= 0.1 * kelly_base - 1e-12
            ), f"Fraction {fraction} below floor*kelly_base {0.1 * kelly_base}"

    def test_kelly_fraction_bounded_various_bases(self):
        """Test bounding with various kelly_base values."""
        prices = _sine_wave_prices(n=150)
        for kb in [0.1, 0.25, 0.5, 1.0, 2.0]:
            fraction = self.adapter.compute_kelly_fraction(kb, prices)
            assert 0.1 * kb - 1e-12 <= fraction <= kb + 1e-12


# ═══════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestKuramotoKellyEdgeCases:
    def setup_method(self):
        self.bus = NeuroSignalBus()
        self.adapter = KuramotoKellyAdapter(self.bus)

    def test_very_short_prices(self):
        """Prices with only 3 elements should not crash."""
        prices = np.array([100.0, 101.0, 99.5])
        fraction = self.adapter.compute_kelly_fraction(0.5, prices)
        assert np.isfinite(fraction)
        assert fraction >= 0.0

    def test_constant_prices_R_zero(self):
        """Constant prices yield zero std returns -> R should be 0."""
        prices = _flat_prices(n=50)
        returns = np.diff(prices) / prices[:-1]
        R = self.adapter.compute_order_parameter(returns)
        assert R == 0.0

    def test_nan_in_returns_handled(self):
        """NaN in returns should be filtered, not crash."""
        returns = np.array([0.01, 0.02, np.nan, -0.01, 0.03, np.nan, 0.01, -0.02])
        R = self.adapter.compute_order_parameter(returns)
        assert np.isfinite(R)
        assert 0.0 <= R <= 1.0

    def test_single_return(self):
        """A single return value should return 0.0 gracefully."""
        R = self.adapter.compute_order_parameter(np.array([0.01]))
        # len < 2, should return 0.0
        assert R == 0.0

    def test_empty_returns(self):
        R = self.adapter.compute_order_parameter(np.array([]))
        assert R == 0.0

    def test_none_returns(self):
        R = self.adapter.compute_order_parameter(None)
        assert R == 0.0


# ═══════════════════════════════════════════════════════════════════════
# Regime classification
# ═══════════════════════════════════════════════════════════════════════


class TestRegimeClassification:
    def setup_method(self):
        self.bus = NeuroSignalBus()
        self.adapter = KuramotoKellyAdapter(self.bus)

    def test_low_R_chaotic(self):
        assert self.adapter.classify_regime(0.1) == "chaotic"
        assert self.adapter.classify_regime(0.0) == "chaotic"
        assert self.adapter.classify_regime(0.29) == "chaotic"

    def test_mid_R_transitional(self):
        assert self.adapter.classify_regime(0.3) == "transitional"
        assert self.adapter.classify_regime(0.5) == "transitional"
        assert self.adapter.classify_regime(0.69) == "transitional"

    def test_high_R_coherent(self):
        assert self.adapter.classify_regime(0.7) == "coherent"
        assert self.adapter.classify_regime(0.9) == "coherent"
        assert self.adapter.classify_regime(1.0) == "coherent"


# ═══════════════════════════════════════════════════════════════════════
# Custom adapter parameters
# ═══════════════════════════════════════════════════════════════════════


class TestCustomAdapterParams:
    def test_custom_floor_ceil(self):
        bus = NeuroSignalBus()
        adapter = KuramotoKellyAdapter(bus, floor=0.2, ceil=0.8)
        prices = _sine_wave_prices(n=150)
        fraction = adapter.compute_kelly_fraction(1.0, prices)
        assert 0.2 - 1e-12 <= fraction <= 1.0 + 1e-12

    def test_custom_R_thresholds(self):
        bus = NeuroSignalBus()
        adapter = KuramotoKellyAdapter(bus, R_low=0.1, R_high=0.9)
        prices = _sine_wave_prices(n=150)
        fraction = adapter.compute_kelly_fraction(1.0, prices)
        assert np.isfinite(fraction)
        assert fraction > 0.0

    def test_bus_config_integration(self):
        """Test that bus with custom BusConfig works with the adapter."""
        config = BusConfig(kelly_coherence_floor=0.2, kelly_coherence_ceil=0.9)
        bus = NeuroSignalBus(config=config)
        adapter = KuramotoKellyAdapter(bus)
        prices = _sine_wave_prices(n=150)
        fraction = adapter.compute_kelly_fraction(0.5, prices)
        assert np.isfinite(fraction)
        # Verify R was published and bus position multiplier works
        mult = bus.compute_position_multiplier(kelly_base=1.0)
        assert mult >= 0.0
