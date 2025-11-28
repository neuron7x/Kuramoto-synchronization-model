"""Tests for enhanced neuromodulator functions in neuromods.py."""

from __future__ import annotations

import pytest

from nak_controller.control.neuromods import (
    NeuromodulatorState,
    acetylcholine,
    cross_modulator_interaction,
    dopamine,
    dopamine_enhanced,
    glutamate_gaba_balance,
    homeostatic_compensation,
    modulate_activity_ach,
    modulate_activity_integrated,
    modulate_risk_da,
    modulate_risk_integrated,
    noradrenaline,
    noradrenaline_enhanced,
    serotonin,
    serotonin_enhanced,
)

# Small value to prevent division by zero in ratio calculations
EPSILON = 1e-9


class TestCoreNeuromodulatorFunctions:
    """Test backward-compatible core neuromodulator functions."""

    def test_dopamine_baseline(self) -> None:
        """Dopamine at zero reward should be at baseline 0.5."""
        result = dopamine(0.0, beta_DA=1.0)
        assert result == pytest.approx(0.5)

    def test_dopamine_positive_reward(self) -> None:
        """Positive unexpected reward increases dopamine."""
        result = dopamine(0.1, beta_DA=1.0)
        assert result > 0.5
        assert result <= 1.0

    def test_dopamine_negative_reward(self) -> None:
        """Negative unexpected reward decreases dopamine."""
        result = dopamine(-0.1, beta_DA=1.0)
        assert result < 0.5
        assert result >= 0.0

    def test_noradrenaline_zero_vol(self) -> None:
        """Zero volatility should produce zero noradrenaline."""
        result = noradrenaline(0.0, na_vol_gain=1.0)
        assert result == pytest.approx(0.0)

    def test_noradrenaline_high_vol(self) -> None:
        """High volatility should produce high noradrenaline."""
        result = noradrenaline(0.8, na_vol_gain=1.0)
        assert result > 0.5

    def test_serotonin_zero_dd(self) -> None:
        """Zero drawdown should produce zero serotonin."""
        result = serotonin(0.0, ht_dd_gain=1.0)
        assert result == pytest.approx(0.0)

    def test_serotonin_high_dd(self) -> None:
        """High drawdown should produce high serotonin."""
        result = serotonin(0.5, ht_dd_gain=1.0)
        assert result > 0.0

    def test_acetylcholine_zero_exposure(self) -> None:
        """Zero exposure should produce baseline acetylcholine."""
        result = acetylcholine(0.0, eta_ACh=1.0)
        assert result == pytest.approx(0.5)

    def test_acetylcholine_high_exposure(self) -> None:
        """High exposure increases acetylcholine."""
        result = acetylcholine(0.5, eta_ACh=1.0)
        assert result > 0.5


class TestEnhancedNeuromodulatorFunctions:
    """Test enhanced neuromodulator functions with improved dynamics."""

    def test_dopamine_enhanced_asymmetry(self) -> None:
        """Enhanced dopamine should show asymmetric loss aversion."""
        pos = dopamine_enhanced(0.1, beta_DA=1.0)
        neg = dopamine_enhanced(-0.1, beta_DA=1.0)
        # Due to 1.5x loss aversion, negative impact should be larger
        pos_delta = pos - 0.5
        neg_delta = 0.5 - neg
        # Loss aversion: negative change should be ~1.5x positive change
        assert neg_delta > pos_delta

    def test_dopamine_enhanced_saturation(self) -> None:
        """Enhanced dopamine should saturate at extremes."""
        high = dopamine_enhanced(10.0, beta_DA=1.0)
        low = dopamine_enhanced(-10.0, beta_DA=1.0)
        assert high == pytest.approx(1.0, abs=0.01)
        assert low == pytest.approx(0.0, abs=0.01)

    def test_noradrenaline_enhanced_weber_fechner(self) -> None:
        """Enhanced noradrenaline should show diminishing returns."""
        low = noradrenaline_enhanced(0.1, na_vol_gain=1.0)
        mid = noradrenaline_enhanced(0.5, na_vol_gain=1.0)
        high = noradrenaline_enhanced(0.9, na_vol_gain=1.0)
        # Due to sqrt, the difference between low-mid should be larger than mid-high
        diff_low_mid = mid - low
        diff_mid_high = high - mid
        assert diff_low_mid > diff_mid_high

    def test_serotonin_enhanced_progressive(self) -> None:
        """Enhanced serotonin should show progressive response."""
        low_dd = serotonin_enhanced(0.1, ht_dd_gain=1.0)
        high_dd = serotonin_enhanced(0.5, ht_dd_gain=1.0)
        # Due to quadratic term, high DD should have more than 5x the effect
        ratio = high_dd / max(low_dd, EPSILON)
        assert ratio > 5


class TestCrossModulatorInteraction:
    """Test cross-modulator interaction dynamics."""

    def test_interaction_preserves_na_ach(self) -> None:
        """NA and ACh should be unchanged by interactions."""
        DA, NA, HT, ACh = cross_modulator_interaction(0.5, 0.6, 0.4, 0.7)
        assert NA == pytest.approx(0.6)
        assert ACh == pytest.approx(0.7)

    def test_interaction_na_enhances_da(self) -> None:
        """High NA should enhance DA signal."""
        baseline_da, _, _, _ = cross_modulator_interaction(0.5, 0.5, 0.5, 0.5)
        high_na_da, _, _, _ = cross_modulator_interaction(0.5, 0.9, 0.5, 0.5)
        assert high_na_da > baseline_da

    def test_interaction_ht_dampens_da(self) -> None:
        """High serotonin should dampen DA signal."""
        baseline_da, _, _, _ = cross_modulator_interaction(0.5, 0.5, 0.5, 0.5)
        high_ht_da, _, _, _ = cross_modulator_interaction(0.5, 0.5, 0.9, 0.5)
        assert high_ht_da < baseline_da

    def test_interaction_da_reduces_ht(self) -> None:
        """High DA should reduce serotonin effect."""
        _, _, baseline_ht, _ = cross_modulator_interaction(0.5, 0.5, 0.5, 0.5)
        _, _, high_da_ht, _ = cross_modulator_interaction(0.9, 0.5, 0.5, 0.5)
        assert high_da_ht < baseline_ht

    def test_interaction_ach_gates_strength(self) -> None:
        """Low ACh should reduce interaction strength."""
        da_high_ach, _, _, _ = cross_modulator_interaction(0.5, 0.9, 0.5, 0.9)
        da_low_ach, _, _, _ = cross_modulator_interaction(0.5, 0.9, 0.5, 0.1)
        # With high NA and low ACh, DA boost should be smaller
        high_ach_boost = da_high_ach - 0.5
        low_ach_boost = da_low_ach - 0.5
        assert low_ach_boost < high_ach_boost


class TestGlutamateGabaBalance:
    """Test excitatory-inhibitory balance computation."""

    def test_balance_baseline(self) -> None:
        """Baseline modulators should produce near-zero balance."""
        balance = glutamate_gaba_balance(0.5, 0.5, 0.5)
        assert balance == pytest.approx(0.0, abs=0.01)

    def test_balance_high_da_excitatory(self) -> None:
        """High DA should produce excitatory balance."""
        balance = glutamate_gaba_balance(0.9, 0.5, 0.5)
        assert balance > 0

    def test_balance_high_ht_inhibitory(self) -> None:
        """High serotonin should produce inhibitory balance."""
        balance = glutamate_gaba_balance(0.5, 0.5, 0.9)
        assert balance < 0

    def test_balance_bounded(self) -> None:
        """Balance should be bounded to [-1, 1]."""
        high_balance = glutamate_gaba_balance(1.0, 1.0, 0.0)
        low_balance = glutamate_gaba_balance(0.0, 0.0, 1.0)
        assert -1.0 <= high_balance <= 1.0
        assert -1.0 <= low_balance <= 1.0


class TestHomeostaticCompensation:
    """Test homeostatic pressure toward baseline."""

    def test_homeostatic_pull_to_baseline(self) -> None:
        """Values above baseline should be pulled down."""
        high = homeostatic_compensation(0.8, target=0.5, rate=0.1)
        assert high < 0.8
        assert high >= 0.5

    def test_homeostatic_push_to_baseline(self) -> None:
        """Values below baseline should be pushed up."""
        low = homeostatic_compensation(0.2, target=0.5, rate=0.1)
        assert low > 0.2
        assert low <= 0.5

    def test_homeostatic_at_baseline(self) -> None:
        """Values at baseline should remain unchanged."""
        at_baseline = homeostatic_compensation(0.5, target=0.5, rate=0.1)
        assert at_baseline == pytest.approx(0.5)

    def test_homeostatic_bounded(self) -> None:
        """Compensation should keep values in [0, 1]."""
        very_high = homeostatic_compensation(0.99, target=0.5, rate=0.5)
        very_low = homeostatic_compensation(0.01, target=0.5, rate=0.5)
        assert 0.0 <= very_high <= 1.0
        assert 0.0 <= very_low <= 1.0


class TestModulationFunctions:
    """Test risk and activity modulation functions."""

    def test_modulate_risk_da_baseline(self) -> None:
        """Baseline DA should not change rate."""
        result = modulate_risk_da(1.0, DA=0.5, da_gain=0.1, r_min=0.5, r_max=1.5)
        assert result == pytest.approx(1.0)

    def test_modulate_risk_integrated_opposing(self) -> None:
        """High DA and high 5-HT should partially cancel."""
        da_only = modulate_risk_integrated(
            1.0, DA=0.9, HT=0.5, da_gain=0.2, ht_dampening=0.2, r_min=0.5, r_max=1.5
        )
        da_ht = modulate_risk_integrated(
            1.0, DA=0.9, HT=0.9, da_gain=0.2, ht_dampening=0.2, r_min=0.5, r_max=1.5
        )
        # With opposing HT, the rate increase should be smaller
        assert da_ht < da_only

    def test_modulate_activity_ach_baseline(self) -> None:
        """Baseline ACh should produce activity near baseline."""
        result = modulate_activity_ach(1.0, ACh=0.5)
        assert result == pytest.approx(1.0)

    def test_modulate_activity_integrated_na_boost(self) -> None:
        """High NA should boost activity."""
        baseline = modulate_activity_integrated(1.0, ACh=0.5, NA=0.5, HT=0.5)
        high_na = modulate_activity_integrated(1.0, ACh=0.5, NA=0.9, HT=0.5)
        assert high_na > baseline

    def test_modulate_activity_integrated_ht_dampen(self) -> None:
        """High serotonin should dampen activity."""
        baseline = modulate_activity_integrated(1.0, ACh=0.5, NA=0.5, HT=0.5)
        high_ht = modulate_activity_integrated(1.0, ACh=0.5, NA=0.5, HT=0.9)
        assert high_ht < baseline


class TestNeuromodulatorState:
    """Test the NeuromodulatorState container class."""

    def test_compute_basic(self) -> None:
        """State computation should produce valid values."""
        state = NeuromodulatorState.compute(
            unexpected_reward=0.0,
            global_vol=0.3,
            portfolio_dd=0.1,
            exposure=0.5,
            beta_DA=1.0,
            na_vol_gain=1.0,
            ht_dd_gain=1.0,
            eta_ACh=1.0,
        )
        assert 0.0 <= state.DA <= 1.0
        assert 0.0 <= state.NA <= 1.0
        assert 0.0 <= state.HT <= 1.0
        assert 0.0 <= state.ACh <= 1.0
        assert -1.0 <= state.balance <= 1.0
        assert state.regime in ("excitatory", "inhibitory", "balanced")

    def test_compute_with_interactions(self) -> None:
        """State with interactions should differ from without."""
        with_interact = NeuromodulatorState.compute(
            unexpected_reward=0.1,
            global_vol=0.5,
            portfolio_dd=0.2,
            exposure=0.6,
            beta_DA=1.0,
            na_vol_gain=1.0,
            ht_dd_gain=1.0,
            eta_ACh=1.0,
            apply_interactions=True,
        )
        without_interact = NeuromodulatorState.compute(
            unexpected_reward=0.1,
            global_vol=0.5,
            portfolio_dd=0.2,
            exposure=0.6,
            beta_DA=1.0,
            na_vol_gain=1.0,
            ht_dd_gain=1.0,
            eta_ACh=1.0,
            apply_interactions=False,
        )
        # At least one modulator should differ
        assert (
            with_interact.DA != without_interact.DA
            or with_interact.HT != without_interact.HT
        )

    def test_compute_with_homeostasis(self) -> None:
        """State with homeostasis should be pulled toward baseline."""
        with_homeo = NeuromodulatorState.compute(
            unexpected_reward=0.5,
            global_vol=0.1,
            portfolio_dd=0.1,
            exposure=0.5,
            beta_DA=1.0,
            na_vol_gain=1.0,
            ht_dd_gain=1.0,
            eta_ACh=1.0,
            apply_interactions=False,
            apply_homeostasis=True,
        )
        without_homeo = NeuromodulatorState.compute(
            unexpected_reward=0.5,
            global_vol=0.1,
            portfolio_dd=0.1,
            exposure=0.5,
            beta_DA=1.0,
            na_vol_gain=1.0,
            ht_dd_gain=1.0,
            eta_ACh=1.0,
            apply_interactions=False,
            apply_homeostasis=False,
        )
        # With homeostasis, DA should be closer to 0.5 than without
        assert abs(with_homeo.DA - 0.5) <= abs(without_homeo.DA - 0.5)

    def test_regime_classification_excitatory(self) -> None:
        """High DA should classify as excitatory regime."""
        state = NeuromodulatorState.compute(
            unexpected_reward=0.5,
            global_vol=0.1,
            portfolio_dd=0.0,
            exposure=0.5,
            beta_DA=1.0,
            na_vol_gain=1.0,
            ht_dd_gain=1.0,
            eta_ACh=1.0,
            apply_interactions=False,
        )
        assert state.regime == "excitatory"

    def test_regime_classification_inhibitory(self) -> None:
        """High drawdown should classify as inhibitory regime."""
        state = NeuromodulatorState.compute(
            unexpected_reward=-0.2,
            global_vol=0.1,
            portfolio_dd=0.8,
            exposure=0.5,
            beta_DA=1.0,
            na_vol_gain=1.0,
            ht_dd_gain=1.0,
            eta_ACh=1.0,
            apply_interactions=False,
        )
        assert state.regime == "inhibitory"
