"""Tests for the calibration constants module."""

from __future__ import annotations

from core.neuro.calibration_constants import (
    DopamineParameterRanges,
    NAKParameterRanges,
    RegimeAdaptiveParameterRanges,
    RiskEngineParameterRanges,
    SerotoninParameterRanges,
    validate_parameter_invariants,
)


class TestParameterRanges:
    """Test parameter range definitions."""

    def test_nak_ranges_are_consistent(self):
        """Verify NAK parameter ranges are logically consistent."""
        ranges = NAKParameterRanges()

        # EI ranges are sensible
        assert ranges.EI_RANGE[0] == 0.0
        assert ranges.EI_RANGE[1] == 1.0
        assert ranges.EI_RANGE[0] < ranges.EI_RANGE[1]

        # Default values are within ranges
        assert ranges.EI_RANGE[0] <= ranges.EI_CRIT_DEFAULT <= ranges.EI_RANGE[1]
        assert ranges.EI_RANGE[0] <= ranges.EI_LOW_DEFAULT <= ranges.EI_RANGE[1]
        assert ranges.EI_RANGE[0] <= ranges.EI_HIGH_DEFAULT <= ranges.EI_RANGE[1]

        # Default thresholds maintain ordering
        assert ranges.EI_CRIT_DEFAULT <= ranges.EI_LOW_DEFAULT
        assert ranges.EI_LOW_DEFAULT < ranges.EI_HIGH_DEFAULT

        # Volatility defaults maintain ordering
        assert ranges.VOL_AMBER_DEFAULT <= ranges.VOL_RED_DEFAULT

        # Drawdown defaults maintain ordering
        assert ranges.DD_AMBER_DEFAULT <= ranges.DD_RED_DEFAULT

    def test_dopamine_ranges_are_consistent(self):
        """Verify Dopamine parameter ranges are logically consistent."""
        ranges = DopamineParameterRanges()

        # Discount gamma is in (0, 1)
        assert 0 < ranges.DISCOUNT_GAMMA_DEFAULT < 1.0

        # Learning rate is positive
        assert ranges.LEARNING_RATE_V_DEFAULT > ranges.LEARNING_RATE_MIN

        # Burst factor is >= 1
        assert ranges.BURST_FACTOR_DEFAULT >= ranges.BURST_FACTOR_MIN

        # Temperature bounds
        assert ranges.BASE_TEMPERATURE_DEFAULT > ranges.TEMPERATURE_MIN
        assert ranges.MIN_TEMPERATURE_DEFAULT >= ranges.TEMPERATURE_MIN
        assert ranges.MIN_TEMPERATURE_DEFAULT <= ranges.BASE_TEMPERATURE_DEFAULT

        # Gate thresholds are in [0, 1]
        for threshold in [
            ranges.INVIGORATION_THRESHOLD_DEFAULT,
            ranges.NO_GO_THRESHOLD_DEFAULT,
            ranges.HOLD_THRESHOLD_DEFAULT
        ]:
            assert 0.0 <= threshold <= 1.0

    def test_serotonin_ranges_are_consistent(self):
        """Verify Serotonin parameter ranges are logically consistent."""
        ranges = SerotoninParameterRanges()

        # Beta ranges are [0, 1]
        assert ranges.BETA_RANGE == (0.0, 1.0)
        assert ranges.BETA_RANGE[0] <= ranges.TONIC_BETA_DEFAULT <= ranges.BETA_RANGE[1]
        assert ranges.BETA_RANGE[0] <= ranges.PHASIC_BETA_DEFAULT <= ranges.BETA_RANGE[1]

        # Stress thresholds maintain ordering
        assert ranges.RELEASE_THRESHOLD_DEFAULT <= ranges.STRESS_THRESHOLD_DEFAULT

        # Floor values maintain ordering
        assert ranges.FLOOR_MIN_DEFAULT <= ranges.FLOOR_MAX_DEFAULT
        assert ranges.FLOOR_RANGE[0] <= ranges.FLOOR_MIN_DEFAULT <= ranges.FLOOR_RANGE[1]
        assert ranges.FLOOR_RANGE[0] <= ranges.FLOOR_MAX_DEFAULT <= ranges.FLOOR_RANGE[1]

        # Desensitization is less than 1
        assert ranges.MAX_DESENSITIZATION_DEFAULT < 1.0

    def test_risk_engine_ranges_are_consistent(self):
        """Verify Risk Engine parameter ranges are logically consistent."""
        ranges = RiskEngineParameterRanges()

        # Loss percent is in (0, 1]
        assert 0 < ranges.MAX_DAILY_LOSS_PERCENT_DEFAULT <= 1.0

        # Leverage is positive
        assert ranges.MAX_LEVERAGE_DEFAULT > ranges.MAX_LEVERAGE_MIN

        # Rate limits
        assert ranges.MAX_ORDERS_PER_MINUTE_DEFAULT >= ranges.MAX_ORDERS_PER_MINUTE_MIN

        # Safe mode multiplier is in [0, 1]
        safe_mult = ranges.SAFE_MODE_POSITION_MULTIPLIER_DEFAULT
        assert ranges.SAFE_MODE_POSITION_MULTIPLIER_RANGE[0] <= safe_mult <= ranges.SAFE_MODE_POSITION_MULTIPLIER_RANGE[1]

        # Kill switch streak is positive
        assert ranges.KILL_SWITCH_LOSS_STREAK_DEFAULT >= ranges.KILL_SWITCH_LOSS_STREAK_MIN

    def test_regime_adaptive_ranges_are_consistent(self):
        """Verify Regime Adaptive parameter ranges are logically consistent."""
        ranges = RegimeAdaptiveParameterRanges()

        # Thresholds maintain ordering
        assert ranges.CALM_THRESHOLD_DEFAULT < ranges.STRESSED_THRESHOLD_DEFAULT < ranges.CRITICAL_THRESHOLD_DEFAULT

        # Multipliers are positive
        assert ranges.CALM_MULTIPLIER_DEFAULT > 0
        assert ranges.STRESSED_MULTIPLIER_DEFAULT > 0
        assert ranges.CRITICAL_MULTIPLIER_DEFAULT > 0

        # Half life is positive
        assert ranges.HALF_LIFE_SECONDS_DEFAULT > ranges.HALF_LIFE_SECONDS_MIN

        # Min samples is at least 1
        assert ranges.MIN_SAMPLES_DEFAULT >= ranges.MIN_SAMPLES_MIN


class TestNAKInvariants:
    """Test NAK controller invariant validation."""

    def test_valid_nak_config_passes(self):
        """Valid NAK configuration passes validation."""
        params = {
            "EI_low": 0.35,
            "EI_high": 0.65,
            "EI_crit": 0.15,
            "vol_amber": 0.70,
            "vol_red": 0.90,
            "dd_amber": 0.40,
            "dd_red": 0.70,
            "delta_r_limit": 0.20,
            "r_min": 0.0,
            "r_max": 1.0,
        }

        is_valid, errors = validate_parameter_invariants("nak", params)
        assert is_valid, f"Should be valid, but got errors: {errors}"
        assert len(errors) == 0

    def test_nak_ei_low_greater_than_high_fails(self):
        """NAK validation fails when EI_low >= EI_high."""
        params = {
            "EI_low": 0.70,
            "EI_high": 0.65,
            "EI_crit": 0.15,
        }

        is_valid, errors = validate_parameter_invariants("nak", params)
        assert not is_valid
        assert len(errors) > 0
        assert any("EI_low" in err and "EI_high" in err for err in errors)

    def test_nak_ei_crit_greater_than_low_fails(self):
        """NAK validation fails when EI_crit > EI_low."""
        params = {
            "EI_low": 0.35,
            "EI_high": 0.65,
            "EI_crit": 0.40,
        }

        is_valid, errors = validate_parameter_invariants("nak", params)
        assert not is_valid
        assert any("EI_crit" in err and "EI_low" in err for err in errors)

    def test_nak_vol_amber_greater_than_red_fails(self):
        """NAK validation fails when vol_amber > vol_red."""
        params = {
            "vol_amber": 0.90,
            "vol_red": 0.70,
        }

        is_valid, errors = validate_parameter_invariants("nak", params)
        assert not is_valid
        assert any("vol_amber" in err and "vol_red" in err for err in errors)

    def test_nak_dd_amber_greater_than_red_fails(self):
        """NAK validation fails when dd_amber > dd_red."""
        params = {
            "dd_amber": 0.70,
            "dd_red": 0.40,
        }

        is_valid, errors = validate_parameter_invariants("nak", params)
        assert not is_valid
        assert any("dd_amber" in err and "dd_red" in err for err in errors)

    def test_nak_delta_r_limit_out_of_range_fails(self):
        """NAK validation fails when delta_r_limit is out of range."""
        # Test zero (must be > 0)
        params = {"delta_r_limit": 0.0}
        is_valid, errors = validate_parameter_invariants("nak", params)
        assert not is_valid

        # Test > 1.0
        params = {"delta_r_limit": 1.5}
        is_valid, errors = validate_parameter_invariants("nak", params)
        assert not is_valid

    def test_nak_r_min_greater_than_max_fails(self):
        """NAK validation fails when r_min >= r_max."""
        params = {
            "r_min": 1.0,
            "r_max": 0.5,
        }

        is_valid, errors = validate_parameter_invariants("nak", params)
        assert not is_valid
        assert any("r_min" in err and "r_max" in err for err in errors)


class TestDopamineInvariants:
    """Test Dopamine controller invariant validation."""

    def test_valid_dopamine_config_passes(self):
        """Valid Dopamine configuration passes validation."""
        params = {
            "discount_gamma": 0.98,
            "learning_rate_v": 0.10,
            "burst_factor": 2.5,
            "base_temperature": 1.0,
            "min_temperature": 0.05,
            "invigoration_threshold": 0.75,
            "no_go_threshold": 0.25,
            "hold_threshold": 0.40,
        }

        is_valid, errors = validate_parameter_invariants("dopamine", params)
        assert is_valid, f"Should be valid, but got errors: {errors}"
        assert len(errors) == 0

    def test_dopamine_discount_gamma_boundary_fails(self):
        """Dopamine validation fails when discount_gamma is at boundary."""
        ranges = DopamineParameterRanges()

        # Test at 0.0 (must be > 0)
        params = {"discount_gamma": ranges.DISCOUNT_GAMMA_RANGE[0]}
        is_valid, errors = validate_parameter_invariants("dopamine", params)
        assert not is_valid

        # Test at 1.0 (must be < 1)
        params = {"discount_gamma": ranges.DISCOUNT_GAMMA_RANGE[1]}
        is_valid, errors = validate_parameter_invariants("dopamine", params)
        assert not is_valid

    def test_dopamine_learning_rate_zero_fails(self):
        """Dopamine validation fails when learning_rate_v <= 0."""
        params = {"learning_rate_v": 0.0}

        is_valid, errors = validate_parameter_invariants("dopamine", params)
        assert not is_valid
        assert any("learning_rate_v" in err for err in errors)

    def test_dopamine_burst_factor_less_than_one_fails(self):
        """Dopamine validation fails when burst_factor < 1.0."""
        params = {"burst_factor": 0.5}

        is_valid, errors = validate_parameter_invariants("dopamine", params)
        assert not is_valid
        assert any("burst_factor" in err for err in errors)

    def test_dopamine_min_temp_greater_than_base_fails(self):
        """Dopamine validation fails when min_temperature > base_temperature."""
        params = {
            "base_temperature": 0.5,
            "min_temperature": 1.0,
        }

        is_valid, errors = validate_parameter_invariants("dopamine", params)
        assert not is_valid
        assert any("min_temperature" in err and "base_temperature" in err for err in errors)

    def test_dopamine_gate_thresholds_out_of_range_fail(self):
        """Dopamine validation fails when gate thresholds are out of [0, 1]."""
        # Test negative
        params = {"invigoration_threshold": -0.1}
        is_valid, errors = validate_parameter_invariants("dopamine", params)
        assert not is_valid

        # Test > 1.0
        params = {"no_go_threshold": 1.5}
        is_valid, errors = validate_parameter_invariants("dopamine", params)
        assert not is_valid


class TestSerotoninInvariants:
    """Test Serotonin controller invariant validation."""

    def test_valid_serotonin_config_passes(self):
        """Valid Serotonin configuration passes validation."""
        params = {
            "tonic_beta": 0.95,
            "phasic_beta": 0.70,
            "stress_threshold": 0.80,
            "release_threshold": 0.50,
            "floor_min": 0.1,
            "floor_max": 0.8,
            "max_desensitization": 0.5,
        }

        is_valid, errors = validate_parameter_invariants("serotonin", params)
        assert is_valid, f"Should be valid, but got errors: {errors}"
        assert len(errors) == 0

    def test_serotonin_beta_out_of_range_fails(self):
        """Serotonin validation fails when beta values are out of [0, 1]."""
        # Test negative
        params = {"tonic_beta": -0.1}
        is_valid, errors = validate_parameter_invariants("serotonin", params)
        assert not is_valid

        # Test > 1.0
        params = {"phasic_beta": 1.5}
        is_valid, errors = validate_parameter_invariants("serotonin", params)
        assert not is_valid

    def test_serotonin_release_greater_than_stress_fails(self):
        """Serotonin validation fails when release_threshold > stress_threshold."""
        params = {
            "stress_threshold": 0.50,
            "release_threshold": 0.80,
        }

        is_valid, errors = validate_parameter_invariants("serotonin", params)
        assert not is_valid
        assert any("release_threshold" in err and "stress_threshold" in err for err in errors)

    def test_serotonin_floor_min_greater_than_max_fails(self):
        """Serotonin validation fails when floor_min > floor_max."""
        params = {
            "floor_min": 0.8,
            "floor_max": 0.1,
        }

        is_valid, errors = validate_parameter_invariants("serotonin", params)
        assert not is_valid
        assert any("floor_min" in err and "floor_max" in err for err in errors)

    def test_serotonin_max_desensitization_at_one_fails(self):
        """Serotonin validation fails when max_desensitization >= 1.0."""
        params = {"max_desensitization": 1.0}

        is_valid, errors = validate_parameter_invariants("serotonin", params)
        assert not is_valid
        assert any("max_desensitization" in err for err in errors)


class TestRiskEngineInvariants:
    """Test Risk Engine invariant validation."""

    def test_valid_risk_engine_config_passes(self):
        """Valid Risk Engine configuration passes validation."""
        params = {
            "max_daily_loss_percent": 0.05,
            "max_leverage": 5.0,
            "max_orders_per_minute": 60,
            "max_orders_per_hour": 500,
            "safe_mode_position_multiplier": 0.25,
            "kill_switch_loss_streak": 5,
        }

        is_valid, errors = validate_parameter_invariants("risk_engine", params)
        assert is_valid, f"Should be valid, but got errors: {errors}"
        assert len(errors) == 0

    def test_risk_engine_max_daily_loss_percent_boundary_fails(self):
        """Risk Engine validation fails at loss percent boundaries."""
        # Test <= 0
        params = {"max_daily_loss_percent": 0.0}
        is_valid, errors = validate_parameter_invariants("risk_engine", params)
        assert not is_valid

        # Test > 1.0
        params = {"max_daily_loss_percent": 1.5}
        is_valid, errors = validate_parameter_invariants("risk_engine", params)
        assert not is_valid

    def test_risk_engine_max_leverage_zero_fails(self):
        """Risk Engine validation fails when max_leverage <= 0."""
        params = {"max_leverage": 0.0}

        is_valid, errors = validate_parameter_invariants("risk_engine", params)
        assert not is_valid
        assert any("max_leverage" in err for err in errors)

    def test_risk_engine_orders_per_minute_greater_than_hour_fails(self):
        """Risk Engine validation fails when orders per minute > per hour."""
        params = {
            "max_orders_per_minute": 100,
            "max_orders_per_hour": 50,
        }

        is_valid, errors = validate_parameter_invariants("risk_engine", params)
        assert not is_valid
        assert any("max_orders_per_minute" in err and "max_orders_per_hour" in err for err in errors)

    def test_risk_engine_safe_mode_multiplier_out_of_range_fails(self):
        """Risk Engine validation fails when safe_mode_position_multiplier is out of [0, 1]."""
        # Test negative
        params = {"safe_mode_position_multiplier": -0.1}
        is_valid, errors = validate_parameter_invariants("risk_engine", params)
        assert not is_valid

        # Test > 1.0
        params = {"safe_mode_position_multiplier": 1.5}
        is_valid, errors = validate_parameter_invariants("risk_engine", params)
        assert not is_valid

    def test_risk_engine_kill_switch_streak_zero_fails(self):
        """Risk Engine validation fails when kill_switch_loss_streak < 1."""
        params = {"kill_switch_loss_streak": 0}

        is_valid, errors = validate_parameter_invariants("risk_engine", params)
        assert not is_valid
        assert any("kill_switch_loss_streak" in err for err in errors)


class TestRegimeAdaptiveInvariants:
    """Test Regime Adaptive Guard invariant validation."""

    def test_valid_regime_adaptive_config_passes(self):
        """Valid Regime Adaptive configuration passes validation."""
        params = {
            "calm_threshold": 0.005,
            "stressed_threshold": 0.020,
            "critical_threshold": 0.040,
            "calm_multiplier": 1.10,
            "stressed_multiplier": 0.65,
            "critical_multiplier": 0.40,
            "half_life_seconds": 120.0,
            "min_samples": 5,
        }

        is_valid, errors = validate_parameter_invariants("regime_adaptive", params)
        assert is_valid, f"Should be valid, but got errors: {errors}"
        assert len(errors) == 0

    def test_regime_adaptive_threshold_ordering_fails(self):
        """Regime Adaptive validation fails when thresholds are not ordered."""
        # calm >= stressed
        params = {
            "calm_threshold": 0.020,
            "stressed_threshold": 0.020,
            "critical_threshold": 0.040,
        }
        is_valid, errors = validate_parameter_invariants("regime_adaptive", params)
        assert not is_valid
        assert any("calm" in err and "stressed" in err and "critical" in err for err in errors)

        # stressed >= critical
        params = {
            "calm_threshold": 0.005,
            "stressed_threshold": 0.040,
            "critical_threshold": 0.020,
        }
        is_valid, errors = validate_parameter_invariants("regime_adaptive", params)
        assert not is_valid

    def test_regime_adaptive_negative_multiplier_fails(self):
        """Regime Adaptive validation fails when multipliers <= 0."""
        params = {"calm_multiplier": 0.0}
        is_valid, errors = validate_parameter_invariants("regime_adaptive", params)
        assert not is_valid

        params = {"stressed_multiplier": -0.5}
        is_valid, errors = validate_parameter_invariants("regime_adaptive", params)
        assert not is_valid

    def test_regime_adaptive_half_life_zero_fails(self):
        """Regime Adaptive validation fails when half_life_seconds <= 0."""
        params = {"half_life_seconds": 0.0}

        is_valid, errors = validate_parameter_invariants("regime_adaptive", params)
        assert not is_valid
        assert any("half_life_seconds" in err for err in errors)

    def test_regime_adaptive_min_samples_zero_fails(self):
        """Regime Adaptive validation fails when min_samples < 1."""
        params = {"min_samples": 0}

        is_valid, errors = validate_parameter_invariants("regime_adaptive", params)
        assert not is_valid
        assert any("min_samples" in err for err in errors)


class TestOtherControllerInvariants:
    """Test other controller invariant validation."""

    def test_rate_limiter_invariants(self):
        """Test Rate Limiter invariant validation."""
        # Valid
        params = {"limit": 100, "window_seconds": 60.0}
        is_valid, errors = validate_parameter_invariants("rate_limiter", params)
        assert is_valid

        # Invalid limit
        params = {"limit": 0}
        is_valid, errors = validate_parameter_invariants("rate_limiter", params)
        assert not is_valid

        # Invalid window
        params = {"window_seconds": 0.0}
        is_valid, errors = validate_parameter_invariants("rate_limiter", params)
        assert not is_valid

    def test_gaba_invariants(self):
        """Test GABA controller invariant validation."""
        # Valid
        params = {"impulse_threshold": 0.7, "inhibition_strength": 0.5}
        is_valid, errors = validate_parameter_invariants("gaba", params)
        assert is_valid

        # Invalid impulse threshold
        params = {"impulse_threshold": -0.1}
        is_valid, errors = validate_parameter_invariants("gaba", params)
        assert not is_valid

        # Invalid inhibition strength (out of range)
        params = {"inhibition_strength": 1.5}
        is_valid, errors = validate_parameter_invariants("gaba", params)
        assert not is_valid

    def test_desensitization_invariants(self):
        """Test Desensitization invariant validation."""
        # Valid
        params = {"min_sensitivity": 0.3, "max_sensitivity": 1.0, "decay_rate": 0.01}
        is_valid, errors = validate_parameter_invariants("desensitization", params)
        assert is_valid

        # min > max
        params = {"min_sensitivity": 0.8, "max_sensitivity": 0.3}
        is_valid, errors = validate_parameter_invariants("desensitization", params)
        assert not is_valid

        # Invalid decay rate
        params = {"decay_rate": -0.1}
        is_valid, errors = validate_parameter_invariants("desensitization", params)
        assert not is_valid


class TestUnknownControllerType:
    """Test handling of unknown controller types."""

    def test_unknown_controller_type_fails(self):
        """Validation fails gracefully for unknown controller types."""
        params = {"some_param": 1.0}

        is_valid, errors = validate_parameter_invariants("unknown_controller", params)
        assert not is_valid
        assert len(errors) > 0
        assert any("Unknown controller type" in err for err in errors)
