# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the calibration utility script."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
import yaml

# Add scripts directory to path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from calibrate_controllers import (
    CALIBRATION_PROFILES,
    apply_calibration_profile,
    load_config,
    save_config,
    validate_config,
)


class TestCalibrationProfiles:
    """Tests for calibration profile definitions."""

    def test_all_profiles_have_required_keys(self):
        """Verify all profiles have description and controller configs."""
        for profile_name, profile_data in CALIBRATION_PROFILES.items():
            assert "description" in profile_data, f"{profile_name} missing description"
            assert isinstance(profile_data["description"], str)

            # Should have at least one controller
            controllers = [k for k in profile_data if k != "description"]
            assert len(controllers) > 0, f"{profile_name} has no controller configs"

    def test_profile_names(self):
        """Verify expected profile names exist."""
        expected_profiles = {"conservative", "balanced", "aggressive"}
        actual_profiles = set(CALIBRATION_PROFILES.keys())
        assert expected_profiles == actual_profiles

    def test_nak_profile_parameters(self):
        """Verify NAK profiles have required parameters."""
        required_params = {
            "EI_low",
            "EI_high",
            "EI_crit",
            "vol_amber",
            "vol_red",
            "dd_amber",
            "dd_red",
            "delta_r_limit",
            "risk_mult",
            "activity_mult",
        }

        for profile_name, profile_data in CALIBRATION_PROFILES.items():
            if "nak" in profile_data:
                nak_params = set(profile_data["nak"].keys())
                assert required_params.issubset(
                    nak_params
                ), f"{profile_name} NAK config missing parameters: {required_params - nak_params}"

    def test_dopamine_profile_parameters(self):
        """Verify dopamine profiles have required parameters."""
        required_params = {
            "learning_rate_v",
            "burst_factor",
            "base_temperature",
            "invigoration_threshold",
            "no_go_threshold",
        }

        for profile_name, profile_data in CALIBRATION_PROFILES.items():
            if "dopamine" in profile_data:
                da_params = set(profile_data["dopamine"].keys())
                assert required_params.issubset(da_params), (
                    f"{profile_name} dopamine config missing parameters: "
                    f"{required_params - da_params}"
                )

    def test_serotonin_profile_parameters(self):
        """Verify serotonin profiles have required parameters."""
        required_params = {
            "stress_threshold",
            "release_threshold",
            "hysteresis",
            "cooldown_ticks",
            "stress_gain",
        }

        for profile_name, profile_data in CALIBRATION_PROFILES.items():
            if "serotonin" in profile_data:
                sero_params = set(profile_data["serotonin"].keys())
                assert required_params.issubset(sero_params), (
                    f"{profile_name} serotonin config missing parameters: "
                    f"{required_params - sero_params}"
                )

    def test_risk_engine_profile_parameters(self):
        """Verify risk_engine profiles have required parameters."""
        required_params = {
            "max_daily_loss_percent",
            "max_leverage",
            "safe_mode_position_multiplier",
            "kill_switch_loss_streak",
        }

        for profile_name, profile_data in CALIBRATION_PROFILES.items():
            if "risk_engine" in profile_data:
                risk_params = set(profile_data["risk_engine"].keys())
                assert required_params.issubset(risk_params), (
                    f"{profile_name} risk_engine config missing parameters: "
                    f"{required_params - risk_params}"
                )

    def test_regime_adaptive_profile_parameters(self):
        """Verify regime_adaptive profiles have required parameters."""
        required_params = {
            "calm_threshold",
            "stressed_threshold",
            "critical_threshold",
            "calm_multiplier",
            "stressed_multiplier",
            "critical_multiplier",
        }

        for profile_name, profile_data in CALIBRATION_PROFILES.items():
            if "regime_adaptive" in profile_data:
                regime_params = set(profile_data["regime_adaptive"].keys())
                assert required_params.issubset(regime_params), (
                    f"{profile_name} regime_adaptive config missing parameters: "
                    f"{required_params - regime_params}"
                )

    def test_nak_threshold_relationships(self):
        """Verify NAK thresholds maintain valid relationships."""
        for profile_name, profile_data in CALIBRATION_PROFILES.items():
            if "nak" not in profile_data:
                continue

            nak = profile_data["nak"]

            # EI thresholds
            assert (
                nak["EI_low"] < nak["EI_high"]
            ), f"{profile_name}: EI_low must be less than EI_high"
            assert nak["EI_crit"] >= 0, f"{profile_name}: EI_crit must be non-negative"
            assert nak["EI_crit"] <= nak["EI_low"], f"{profile_name}: EI_crit should be <= EI_low"

            # Volatility thresholds
            assert (
                nak["vol_amber"] <= nak["vol_red"]
            ), f"{profile_name}: vol_amber must be <= vol_red"

            # Drawdown thresholds
            assert nak["dd_amber"] <= nak["dd_red"], f"{profile_name}: dd_amber must be <= dd_red"

            # Delta r limit
            assert (
                0 < nak["delta_r_limit"] <= 1.0
            ), f"{profile_name}: delta_r_limit must be in (0, 1]"

    def test_serotonin_threshold_relationships(self):
        """Verify Serotonin thresholds maintain valid relationships."""
        for profile_name, profile_data in CALIBRATION_PROFILES.items():
            if "serotonin" not in profile_data:
                continue

            sero = profile_data["serotonin"]

            # Stress thresholds
            assert (
                sero["release_threshold"] <= sero["stress_threshold"]
            ), f"{profile_name}: release_threshold must be <= stress_threshold"

            # Hysteresis is reasonable
            assert 0 <= sero["hysteresis"] <= 1.0, f"{profile_name}: hysteresis must be in [0, 1]"

            # Cooldown is non-negative
            assert sero["cooldown_ticks"] >= 0, f"{profile_name}: cooldown_ticks must be >= 0"

    def test_risk_engine_invariants(self):
        """Verify Risk Engine parameters maintain valid relationships."""
        for profile_name, profile_data in CALIBRATION_PROFILES.items():
            if "risk_engine" not in profile_data:
                continue

            risk = profile_data["risk_engine"]

            # Loss percent is in (0, 1]
            assert (
                0 < risk["max_daily_loss_percent"] <= 1.0
            ), f"{profile_name}: max_daily_loss_percent must be in (0, 1]"

            # Leverage is positive
            assert risk["max_leverage"] > 0, f"{profile_name}: max_leverage must be > 0"

            # Safe mode multiplier is in [0, 1]
            assert (
                0 <= risk["safe_mode_position_multiplier"] <= 1.0
            ), f"{profile_name}: safe_mode_position_multiplier must be in [0, 1]"

            # Kill switch streak is positive
            assert (
                risk["kill_switch_loss_streak"] >= 1
            ), f"{profile_name}: kill_switch_loss_streak must be >= 1"

    def test_regime_adaptive_threshold_ordering(self):
        """Verify Regime Adaptive thresholds maintain proper ordering."""
        for profile_name, profile_data in CALIBRATION_PROFILES.items():
            if "regime_adaptive" not in profile_data:
                continue

            regime = profile_data["regime_adaptive"]

            # Threshold ordering: calm < stressed < critical
            assert (
                regime["calm_threshold"]
                < regime["stressed_threshold"]
                < regime["critical_threshold"]
            ), f"{profile_name}: thresholds must satisfy calm < stressed < critical"

            # Multipliers are positive
            assert regime["calm_multiplier"] > 0, f"{profile_name}: calm_multiplier must be > 0"
            assert (
                regime["stressed_multiplier"] > 0
            ), f"{profile_name}: stressed_multiplier must be > 0"
            assert (
                regime["critical_multiplier"] > 0
            ), f"{profile_name}: critical_multiplier must be > 0"


class TestConfigLoading:
    """Tests for configuration file loading and saving."""

    def test_load_save_roundtrip(self):
        """Test loading and saving preserves config structure."""
        test_config = {
            "nak": {
                "EI_low": 0.35,
                "EI_high": 0.65,
                "risk_mult": {"GREEN": 1.0, "AMBER": 0.65, "RED": 0.0},
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)
            save_config(test_config, temp_path)

        try:
            loaded_config = load_config(temp_path)
            assert loaded_config == test_config
        finally:
            temp_path.unlink()

    def test_load_nonexistent_file(self):
        """Test loading nonexistent file raises appropriate error."""
        with pytest.raises(FileNotFoundError):
            load_config(Path("/nonexistent/path/config.yaml"))


class TestValidation:
    """Tests for configuration validation."""

    def test_validate_good_nak_config(self):
        """Test validation passes for valid NAK config."""
        config = {
            "nak": {
                "EI_low": 0.35,
                "EI_high": 0.65,
                "EI_crit": 0.15,
                "vol_amber": 0.7,
                "vol_red": 0.9,
                "dd_amber": 0.4,
                "dd_red": 0.7,
                "delta_r_limit": 0.2,
                "r_min": 0.2,
                "r_max": 1.8,
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)
            yaml.dump(config, f)

        try:
            assert validate_config(temp_path) is True
        finally:
            temp_path.unlink()

    def test_validate_bad_ei_thresholds(self):
        """Test validation fails when EI_low >= EI_high."""
        config = {
            "nak": {
                "EI_low": 0.7,
                "EI_high": 0.65,
                "EI_crit": 0.15,
                "vol_amber": 0.7,
                "vol_red": 0.9,
                "dd_amber": 0.4,
                "dd_red": 0.7,
                "delta_r_limit": 0.2,
                "r_min": 0.2,
                "r_max": 1.8,
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)
            yaml.dump(config, f)

        try:
            assert validate_config(temp_path) is False
        finally:
            temp_path.unlink()

    def test_validate_good_dopamine_config(self):
        """Test validation passes for valid dopamine config."""
        config = {
            "discount_gamma": 0.98,
            "learning_rate_v": 0.1,
            "burst_factor": 2.5,
            "base_temperature": 1.0,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)
            yaml.dump(config, f)

        try:
            assert validate_config(temp_path) is True
        finally:
            temp_path.unlink()

    def test_validate_bad_discount_gamma(self):
        """Test validation fails for invalid discount_gamma."""
        config = {
            "discount_gamma": 1.5,  # Must be < 1.0
            "learning_rate_v": 0.1,
            "burst_factor": 2.5,
            "base_temperature": 1.0,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)
            yaml.dump(config, f)

        try:
            assert validate_config(temp_path) is False
        finally:
            temp_path.unlink()


class TestProfileApplication:
    """Tests for applying calibration profiles."""

    def test_apply_nak_balanced_profile(self):
        """Test applying balanced profile to NAK controller."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_nak.yaml"

            # Need to mock the base config loading
            import calibrate_controllers

            original_load = calibrate_controllers.load_config

            def mock_load(path):
                if "nak.yaml" in str(path):
                    return {
                        "nak": {
                            "L_min": 0.0,
                            "L_max": 1.0,
                            "E_max": 1.0,
                        }
                    }
                return original_load(path)

            calibrate_controllers.load_config = mock_load

            try:
                apply_calibration_profile("nak", "balanced", output_path)

                assert output_path.exists()
                config = load_config(output_path)

                assert "nak" in config
                assert config["nak"]["EI_low"] == 0.35
                assert config["nak"]["EI_high"] == 0.65
                assert config["nak"]["vol_amber"] == 0.7
            finally:
                calibrate_controllers.load_config = original_load

    def test_apply_invalid_profile(self):
        """Test applying nonexistent profile raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.yaml"

            with pytest.raises(SystemExit):
                apply_calibration_profile("nak", "nonexistent", output_path)

    def test_apply_invalid_controller(self):
        """Test applying profile to unsupported controller raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.yaml"

            with pytest.raises(SystemExit):
                apply_calibration_profile("unknown", "balanced", output_path)


class TestProfileCharacteristics:
    """Tests verifying profile characteristics match their intent."""

    def test_conservative_is_most_restrictive(self):
        """Verify conservative profile has tightest constraints."""
        conservative_nak = CALIBRATION_PROFILES["conservative"]["nak"]
        balanced_nak = CALIBRATION_PROFILES["balanced"]["nak"]
        CALIBRATION_PROFILES["aggressive"]["nak"]

        # Conservative should have higher EI thresholds
        assert conservative_nak["EI_low"] >= balanced_nak["EI_low"]
        assert conservative_nak["EI_crit"] >= balanced_nak["EI_crit"]

        # Conservative should have lower volatility/drawdown thresholds
        assert conservative_nak["vol_amber"] <= balanced_nak["vol_amber"]
        assert conservative_nak["dd_amber"] <= balanced_nak["dd_amber"]

        # Conservative should have lower risk multipliers
        assert conservative_nak["risk_mult"]["AMBER"] <= balanced_nak["risk_mult"]["AMBER"]

    def test_aggressive_is_most_permissive(self):
        """Verify aggressive profile has loosest constraints."""
        balanced_nak = CALIBRATION_PROFILES["balanced"]["nak"]
        aggressive_nak = CALIBRATION_PROFILES["aggressive"]["nak"]

        # Aggressive should have lower EI thresholds
        assert aggressive_nak["EI_low"] <= balanced_nak["EI_low"]
        assert aggressive_nak["EI_crit"] <= balanced_nak["EI_crit"]

        # Aggressive should have higher volatility/drawdown thresholds
        assert aggressive_nak["vol_amber"] >= balanced_nak["vol_amber"]
        assert aggressive_nak["dd_amber"] >= balanced_nak["dd_amber"]

        # Aggressive should have higher risk multipliers
        assert aggressive_nak["risk_mult"]["AMBER"] >= balanced_nak["risk_mult"]["AMBER"]

    def test_dopamine_temperature_ordering(self):
        """Verify dopamine temperature follows expected ordering."""
        conservative_da = CALIBRATION_PROFILES["conservative"]["dopamine"]
        balanced_da = CALIBRATION_PROFILES["balanced"]["dopamine"]
        aggressive_da = CALIBRATION_PROFILES["aggressive"]["dopamine"]

        # Aggressive should have highest exploration temperature
        assert conservative_da["base_temperature"] < balanced_da["base_temperature"]
        assert balanced_da["base_temperature"] < aggressive_da["base_temperature"]

        # Aggressive should have lowest gating thresholds
        assert aggressive_da["invigoration_threshold"] <= balanced_da["invigoration_threshold"]
        assert aggressive_da["no_go_threshold"] <= balanced_da["no_go_threshold"]


class TestErrorPaths:
    """Tests for error conditions and edge cases."""

    def test_validate_missing_nak_params(self):
        """Test validation fails when NAK parameters are missing."""
        config = {
            "nak": {
                "EI_low": 0.35,
                # Missing other required params
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)
            yaml.dump(config, f)

        try:
            assert validate_config(temp_path) is False
        finally:
            temp_path.unlink()

    def test_validate_missing_dopamine_params(self):
        """Test validation fails when dopamine parameters are missing."""
        config = {
            "learning_rate_v": 0.1,
            # Missing other required params
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)
            yaml.dump(config, f)

        try:
            assert validate_config(temp_path) is False
        finally:
            temp_path.unlink()

    def test_validate_vol_amber_greater_than_red(self):
        """Test validation fails when vol_amber > vol_red."""
        config = {
            "nak": {
                "EI_low": 0.35,
                "EI_high": 0.65,
                "EI_crit": 0.15,
                "vol_amber": 0.9,  # Greater than vol_red
                "vol_red": 0.7,
                "dd_amber": 0.4,
                "dd_red": 0.7,
                "delta_r_limit": 0.2,
                "r_min": 0.2,
                "r_max": 1.8,
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)
            yaml.dump(config, f)

        try:
            assert validate_config(temp_path) is False
        finally:
            temp_path.unlink()

    def test_validate_nonexistent_file(self):
        """Test validation fails gracefully for nonexistent file."""
        result = validate_config(Path("/nonexistent/file.yaml"))
        assert result is False

    def test_apply_profile_with_controller_not_in_profile(self):
        """Test applying profile without controller exits with error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.yaml"

            with pytest.raises(SystemExit) as exc_info:
                # This should fail because 'unknown' is not a valid controller
                apply_calibration_profile("unknown", "balanced", output_path)
            assert exc_info.value.code == 1
