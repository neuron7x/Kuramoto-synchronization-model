# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Enhanced precision tests for DopamineController.

This module provides comprehensive tests for numeric precision,
boundary conditions, and edge cases in the DopamineController.

Test Coverage:
- RPE computation precision at boundary values
- Temperature calculation stability
- Gate threshold monotonicity
- State persistence round-trip accuracy
- DDM adapter integration precision
"""

from __future__ import annotations

import math
from typing import Dict

import pytest
import yaml

from tradepulse.core.neuro.dopamine.dopamine_controller import DopamineController


@pytest.fixture
def base_config() -> Dict[str, object]:
    """Base configuration for tests."""
    return {
        "version": "3.0",
        "discount_gamma": 0.98,
        "learning_rate_v": 0.1,
        "decay_rate": 0.05,
        "burst_factor": 2.5,
        "k": 1.1,
        "theta": 0.5,
        "w_r": 0.60,
        "w_n": 0.20,
        "w_m": 0.15,
        "w_v": 0.15,
        "novelty_mode": "abs_rpe",
        "c_absrpe": 0.10,
        "baseline": 0.5,
        "delta_gain": 0.5,
        "base_temperature": 1.0,
        "min_temperature": 0.05,
        "temp_k": 1.2,
        "neg_rpe_temp_gain": 0.5,
        "max_temp_multiplier": 3.0,
        "invigoration_threshold": 0.75,
        "no_go_threshold": 0.25,
        "hold_threshold": 0.4,
        "target_dd": -0.05,
        "target_sharpe": 1.0,
        "meta_cooldown_ticks": 5,
        "metric_interval": 1,
        "meta_adapt_rules": {
            "good": {
                "learning_rate_v": 1.01,
                "delta_gain": 1.01,
                "base_temperature": 0.99,
            },
            "bad": {
                "learning_rate_v": 0.99,
                "delta_gain": 0.99,
                "base_temperature": 1.01,
            },
            "neutral": {
                "learning_rate_v": 1.0,
                "delta_gain": 1.0,
                "base_temperature": 1.0,
            },
        },
    }


@pytest.fixture
def controller(tmp_path, base_config) -> DopamineController:
    """Create controller instance for tests."""
    cfg_path = tmp_path / "dopamine.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(base_config, f)
    return DopamineController(str(cfg_path))


class TestRPEComputationPrecision:
    """Tests for RPE computation precision and edge cases."""

    def test_rpe_zero_reward_zero_value(self, controller: DopamineController) -> None:
        """Test RPE computation with all zeros."""
        rpe = controller.compute_rpe(0.0, 0.0, 0.0)
        assert rpe == 0.0
        assert math.isfinite(rpe)

    def test_rpe_with_unity_gamma(self, controller: DopamineController) -> None:
        """Test RPE with gamma = 1 (no discounting)."""
        reward = 0.5
        value = 0.3
        next_value = 0.4

        rpe = controller.compute_rpe(reward, value, next_value, discount_gamma=1.0)

        # δ = r + γ·V' − V = 0.5 + 1.0 * 0.4 - 0.3 = 0.6
        expected = reward + 1.0 * next_value - value
        assert math.isclose(rpe, expected, rel_tol=1e-10)

    def test_rpe_precision_small_values(self, controller: DopamineController) -> None:
        """Test RPE precision with very small values."""
        rpe = controller.compute_rpe(1e-10, 1e-10, 1e-10)
        assert math.isfinite(rpe)
        assert abs(rpe) < 1e-8  # Should be very small

    def test_rpe_precision_large_values(self, controller: DopamineController) -> None:
        """Test RPE precision with large values."""
        rpe = controller.compute_rpe(1e6, 1e6, 1e6)
        assert math.isfinite(rpe)

    def test_rpe_sign_positive_surprise(self, controller: DopamineController) -> None:
        """Test RPE sign for positive surprise (better than expected)."""
        # High reward, low value estimate
        rpe = controller.compute_rpe(1.0, 0.1, 0.1)
        assert rpe > 0  # Positive surprise

    def test_rpe_sign_negative_surprise(self, controller: DopamineController) -> None:
        """Test RPE sign for negative surprise (worse than expected)."""
        # Low reward, high value estimate
        rpe = controller.compute_rpe(0.0, 1.0, 0.0)
        assert rpe < 0  # Negative surprise

    def test_rpe_gamma_boundary_lower(self, controller: DopamineController) -> None:
        """Test RPE with gamma at lower boundary."""
        # Gamma just above 0
        rpe = controller.compute_rpe(0.5, 0.2, 0.3, discount_gamma=0.01)
        assert math.isfinite(rpe)

    def test_rpe_gamma_invalid_raises(self, controller: DopamineController) -> None:
        """Test RPE raises for invalid gamma values."""
        with pytest.raises(ValueError, match="discount_gamma must be in"):
            controller.compute_rpe(0.5, 0.2, 0.3, discount_gamma=0.0)

        with pytest.raises(ValueError, match="discount_gamma must be in"):
            controller.compute_rpe(0.5, 0.2, 0.3, discount_gamma=1.5)


class TestTemperatureCalculationStability:
    """Tests for temperature calculation stability."""

    def test_temperature_bounds_respected(self, controller: DopamineController) -> None:
        """Test temperature stays within configured bounds."""
        min_temp, max_temp = controller.temperature_bounds()

        for da_signal in [0.0, 0.25, 0.5, 0.75, 1.0]:
            controller.last_rpe = 0.0  # Reset RPE to avoid temp boost
            temp = controller.compute_temperature(da_signal)
            assert min_temp <= temp <= max_temp

    def test_temperature_monotonic_with_positive_rpe(
        self, controller: DopamineController
    ) -> None:
        """Test temperature decreases monotonically with increasing DA (positive RPE)."""
        controller.last_rpe = 0.1  # Positive RPE

        temps = []
        for da in [0.0, 0.25, 0.5, 0.75, 1.0]:
            temp = controller.compute_temperature(da)
            temps.append(temp)

        # Each temperature should be <= previous (monotonic decrease)
        for i in range(1, len(temps)):
            assert temps[i] <= temps[i - 1] + 1e-10  # Small tolerance

    def test_temperature_boost_on_negative_rpe(
        self, controller: DopamineController
    ) -> None:
        """Test temperature increases on negative RPE."""
        da_signal = 0.5

        # Baseline temperature (zero RPE)
        controller.last_rpe = 0.0
        temp_baseline = controller.compute_temperature(da_signal)

        # Temperature with negative RPE
        controller.last_rpe = -0.5
        temp_neg_rpe = controller.compute_temperature(da_signal)

        assert temp_neg_rpe >= temp_baseline

    def test_temperature_precision_extreme_da(
        self, controller: DopamineController
    ) -> None:
        """Test temperature calculation with extreme DA values."""
        controller.last_rpe = 0.0

        # DA at 0
        temp_zero = controller.compute_temperature(0.0)
        assert math.isfinite(temp_zero)

        # DA at 1
        temp_one = controller.compute_temperature(1.0)
        assert math.isfinite(temp_one)

        # Verify monotonicity
        assert temp_zero >= temp_one


class TestGateThresholdMonotonicity:
    """Tests for gate threshold monotonicity constraints."""

    def test_threshold_ordering(self, controller: DopamineController) -> None:
        """Test that go >= hold >= no_go thresholds are maintained."""
        cfg = controller.config

        go_threshold = cfg["invigoration_threshold"]
        hold_threshold = cfg["hold_threshold"]
        no_go_threshold = cfg["no_go_threshold"]

        # Verify monotonic ordering
        assert go_threshold >= hold_threshold
        assert hold_threshold >= no_go_threshold

    def test_gate_states_mutual_exclusivity(
        self, controller: DopamineController
    ) -> None:
        """Test gate states follow logical constraints."""
        # High DA - should trigger GO
        da_high = 0.9
        go = controller.check_invigoration(da_high)
        suppress = controller.check_suppress(da_high)

        # Can't be both GO and suppressed simultaneously at high DA
        if go:
            assert not suppress

        # Low DA - should trigger suppression
        da_low = 0.1
        go_low = controller.check_invigoration(da_low)
        suppress_low = controller.check_suppress(da_low)

        assert suppress_low
        assert not go_low


class TestStatePersistencePrecision:
    """Tests for state persistence round-trip precision."""

    def test_state_roundtrip_preserves_precision(
        self, controller: DopamineController
    ) -> None:
        """Test state dump/load preserves numeric precision."""
        # Set some state
        controller.tonic_level = 0.123456789
        controller.phasic_level = 0.987654321
        controller.dopamine_level = 0.555555555
        controller.value_estimate = -0.111111111
        controller.last_rpe = 0.222222222
        controller._adaptive_base_temperature = 1.333333333
        controller._rpe_mean = 0.444444444
        controller._rpe_sq_mean = 0.666666666
        controller._temp_adam_m = 0.0001
        controller._temp_adam_v = 0.0002
        controller._temp_adam_t = 42
        controller._release_gate_open = True
        controller._last_temperature = 0.777777777

        # Dump and load
        state = controller.dump_state()
        controller.reset_state()
        controller.load_state(state)

        # Verify precision is preserved
        assert math.isclose(controller.tonic_level, 0.123456789, rel_tol=1e-10)
        assert math.isclose(controller.phasic_level, 0.987654321, rel_tol=1e-10)
        assert math.isclose(controller.dopamine_level, 0.555555555, rel_tol=1e-10)
        assert math.isclose(controller.value_estimate, -0.111111111, rel_tol=1e-10)
        assert math.isclose(controller.last_rpe, 0.222222222, rel_tol=1e-10)

    def test_state_roundtrip_boundary_values(
        self, controller: DopamineController
    ) -> None:
        """Test state roundtrip with boundary values."""
        # Set boundary values
        controller.tonic_level = 0.0
        controller.phasic_level = 0.0
        controller.dopamine_level = 1.0  # Maximum
        controller.value_estimate = 0.0
        controller.last_rpe = 0.0
        controller._adaptive_base_temperature = 0.2  # Min allowed
        controller._rpe_mean = 0.0
        controller._rpe_sq_mean = 0.0
        controller._temp_adam_m = 0.0
        controller._temp_adam_v = 0.0
        controller._temp_adam_t = 0
        controller._release_gate_open = False
        controller._last_temperature = 0.05  # Min temperature

        state = controller.dump_state()
        controller.reset_state()
        controller.load_state(state)

        # Verify boundary values preserved
        assert controller.dopamine_level == 1.0
        assert controller._release_gate_open is False


class TestDDMIntegrationPrecision:
    """Tests for DDM adapter integration precision."""

    def test_step_with_ddm_params(self, controller: DopamineController) -> None:
        """Test step function with DDM parameters."""
        appetitive = controller.estimate_appetitive_state(0.4, 0.2, 0.1, 0.05)

        rpe, temp, scaled_policy, extras = controller.step(
            reward=0.5,
            value=0.2,
            next_value=0.3,
            appetitive_state=appetitive,
            policy_logits=(0.1, 0.2, 0.3),
            ddm_params=(0.8, 1.0, 0.2),  # v, a, t0
        )

        # Verify all outputs are finite
        assert math.isfinite(rpe)
        assert math.isfinite(temp)
        assert all(math.isfinite(p) for p in scaled_policy)

        # Verify extras contain DDM info
        assert "ddm_thresholds" in extras
        assert "ddm_scale" in extras
        assert math.isfinite(extras["ddm_scale"])

    def test_step_without_ddm_params(self, controller: DopamineController) -> None:
        """Test step function without DDM parameters."""
        appetitive = controller.estimate_appetitive_state(0.4, 0.2, 0.1, 0.05)

        rpe, temp, scaled_policy, extras = controller.step(
            reward=0.5,
            value=0.2,
            next_value=0.3,
            appetitive_state=appetitive,
            policy_logits=(0.1, 0.2, 0.3),
        )

        # Verify all outputs are finite
        assert math.isfinite(rpe)
        assert math.isfinite(temp)
        assert all(math.isfinite(p) for p in scaled_policy)

        # DDM info should not be present
        assert "ddm_thresholds" not in extras


class TestAppetitiveStateComputation:
    """Tests for appetitive state computation precision."""

    def test_appetitive_state_weights_sum(self, controller: DopamineController) -> None:
        """Test appetitive state respects weight configuration."""
        cfg = controller.config

        # All inputs at 1.0
        appetitive = controller.estimate_appetitive_state(1.0, 1.0, 1.0, 1.0)

        # Should be weighted sum (with novelty enhancement from abs_rpe mode)
        expected_min = cfg["w_r"] + cfg["w_n"] + cfg["w_m"] + cfg["w_v"]
        assert appetitive >= expected_min

    def test_appetitive_state_zero_inputs(self, controller: DopamineController) -> None:
        """Test appetitive state with zero inputs."""
        appetitive = controller.estimate_appetitive_state(0.0, 0.0, 0.0, 0.0)
        assert appetitive == 0.0

    def test_appetitive_state_individual_contributions(
        self, controller: DopamineController
    ) -> None:
        """Test each input contributes correctly to appetitive state."""
        controller.last_rpe = 0.0  # Clear RPE for clean test

        # Only reward contribution
        app_r = controller.estimate_appetitive_state(1.0, 0.0, 0.0, 0.0)

        # Only novelty contribution (not asserted due to c_absrpe interaction)
        _app_n = controller.estimate_appetitive_state(0.0, 1.0, 0.0, 0.0)

        # Only momentum contribution
        app_m = controller.estimate_appetitive_state(0.0, 0.0, 1.0, 0.0)

        # Only value_gap contribution
        app_v = controller.estimate_appetitive_state(0.0, 0.0, 0.0, 1.0)

        cfg = controller.config
        assert math.isclose(app_r, cfg["w_r"], rel_tol=1e-10)
        # Note: novelty may include c_absrpe contribution even with 0 input
        assert app_m == pytest.approx(cfg["w_m"], rel=1e-10)
        assert app_v == pytest.approx(cfg["w_v"], rel=1e-10)


class TestValueEstimateUpdate:
    """Tests for value estimate update precision."""

    def test_value_update_td_learning(self, controller: DopamineController) -> None:
        """Test value estimate follows TD learning rule."""
        controller.value_estimate = 0.5
        rpe = 0.2
        controller.last_rpe = rpe
        lr = controller.config["learning_rate_v"]

        expected = 0.5 + lr * rpe
        actual = controller.update_value_estimate(rpe)

        assert math.isclose(actual, expected, rel_tol=1e-10)

    def test_value_update_converges(self, controller: DopamineController) -> None:
        """Test value estimate converges with consistent rewards."""
        controller.value_estimate = 0.0
        target_value = 1.0

        # Repeatedly update toward target
        for _ in range(100):
            rpe = target_value - controller.value_estimate
            controller.update_value_estimate(rpe)

        # Should approach target value
        assert controller.value_estimate > 0.9


class TestMetaAdaptation:
    """Tests for meta-adaptation mechanism precision."""

    def test_meta_adapt_good_performance(self, controller: DopamineController) -> None:
        """Test meta-adaptation with good performance."""
        initial_lr = controller.config["learning_rate_v"]
        initial_dg = controller.config["delta_gain"]
        initial_temp = controller.config["base_temperature"]

        # Good performance: high sharpe, acceptable drawdown
        controller.meta_adapt({"drawdown": -0.03, "sharpe": 1.2})

        # Learning rate and delta_gain should increase
        assert controller.config["learning_rate_v"] > initial_lr
        assert controller.config["delta_gain"] > initial_dg
        # Temperature should decrease
        assert controller.config["base_temperature"] < initial_temp

    def test_meta_adapt_bad_performance(self, controller: DopamineController) -> None:
        """Test meta-adaptation with bad performance."""
        initial_lr = controller.config["learning_rate_v"]
        controller._meta_cooldown_counter = 0  # Bypass cooldown

        # Bad performance: low sharpe, deep drawdown
        controller.meta_adapt({"drawdown": -0.15, "sharpe": 0.3})

        # Learning rate should decrease
        assert controller.config["learning_rate_v"] < initial_lr

    def test_meta_adapt_cooldown_respected(
        self, controller: DopamineController
    ) -> None:
        """Test meta-adaptation respects cooldown."""
        # First adaptation (good performance)
        controller.meta_adapt({"drawdown": -0.03, "sharpe": 1.2})
        lr_after_first = controller.config["learning_rate_v"]

        # Second adaptation during cooldown should be skipped
        controller.meta_adapt({"drawdown": -0.15, "sharpe": 0.3})
        lr_after_second = controller.config["learning_rate_v"]

        # Should be unchanged due to cooldown
        assert lr_after_second == lr_after_first


class TestDopamineSignalBounds:
    """Tests for dopamine signal bounds."""

    def test_dopamine_signal_clamped_high(self, controller: DopamineController) -> None:
        """Test dopamine signal is clamped at upper bound."""
        # Very high appetitive state and positive RPE
        controller.compute_rpe(1000.0, 0.0, 0.0)
        da = controller.compute_dopamine_signal(100.0, controller.last_rpe)

        assert da <= 1.0
        assert da >= 0.0

    def test_dopamine_signal_clamped_low(self, controller: DopamineController) -> None:
        """Test dopamine signal is clamped at lower bound."""
        # Very low appetitive state and negative RPE
        controller.compute_rpe(-1000.0, 100.0, 0.0)
        da = controller.compute_dopamine_signal(0.0, controller.last_rpe)

        assert da <= 1.0
        assert da >= 0.0

    def test_dopamine_signal_finite_always(
        self, controller: DopamineController
    ) -> None:
        """Test dopamine signal is always finite."""
        test_cases = [
            (0.0, 0.0),
            (1.0, 0.5),
            (100.0, 10.0),
            (0.001, -0.5),
        ]

        for appetitive, rpe in test_cases:
            controller.last_rpe = rpe
            da = controller.compute_dopamine_signal(appetitive, rpe)
            assert math.isfinite(da)
