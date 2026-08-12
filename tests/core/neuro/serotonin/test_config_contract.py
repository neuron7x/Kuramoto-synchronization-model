# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for serotonin configuration contract.

This module tests the multi-profile config loading, validation, and
backwards compatibility for the serotonin controller configuration.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from core.neuro.serotonin import (
    SerotoninConfig,
    SerotoninConfigEnvelope,
    SerotoninController,
    SerotoninLegacyConfig,
)


class TestSerotoninConfigEnvelope:
    """Tests for SerotoninConfigEnvelope validation."""

    def test_v24_profile_validation(self):
        """Test that v24 profile is properly validated."""
        config = {
            "active_profile": "v24",
            "serotonin_v24": {
                "alpha": 0.5,
                "beta": 0.3,
                "gamma": 0.4,
                "delta_rho": 0.2,
                "k": 1.5,
                "theta": 0.0,
                "delta": 0.5,
                "za_bias": 0.0,
                "decay_rate": 0.01,
                "cooldown_threshold": 0.7,
                "desens_threshold_ticks": 3,
                "desens_rate": 0.05,
                "target_dd": 0.15,
                "target_sharpe": 1.5,
                "beta_temper": 0.5,
                "phase_threshold": 0.7,
                "phase_kappa": 2.0,
                "burst_factor": 0.35,
                "mod_t_max": 10.0,
                "mod_t_half": 5.0,
                "mod_k": 0.5,
                "max_desens_counter": 10,
                "desens_gain": 0.8,
                "gate_veto": 0.9,
                "phasic_veto": 1.0,
                "temperature_floor_min": 0.1,
                "temperature_floor_max": 0.6,
                "hysteresis_margin": 0.05,
            },
        }
        envelope = SerotoninConfigEnvelope.model_validate(config)
        assert envelope.active_profile == "v24"
        assert envelope.serotonin_v24 is not None

    def test_legacy_profile_validation(self):
        """Test that legacy profile is properly validated."""
        config = {
            "active_profile": "legacy",
            "serotonin_legacy": {
                "tonic_beta": 0.35,
                "phasic_beta": 0.55,
                "stress_gain": 1.0,
                "drawdown_gain": 1.2,
                "novelty_gain": 0.6,
                "stress_threshold": 0.7,
                "release_threshold": 0.4,
                "hysteresis": 0.1,
                "cooldown_ticks": 3,
                "chronic_window": 6,
                "desensitization_rate": 0.05,
                "desensitization_decay": 0.05,
                "max_desensitization": 0.6,
                "floor_min": 0.1,
                "floor_max": 0.6,
                "floor_gain": 0.8,
                "cooldown_extension": 2,
            },
        }
        envelope = SerotoninConfigEnvelope.model_validate(config)
        assert envelope.active_profile == "legacy"
        assert envelope.serotonin_legacy is not None

    def test_multi_profile_config_validation(self):
        """Test config with both profiles defined but one active."""
        config = {
            "active_profile": "v24",
            "serotonin_v24": {
                "alpha": 0.5,
                "beta": 0.3,
                "gamma": 0.4,
                "delta_rho": 0.2,
                "k": 1.5,
                "theta": 0.0,
                "delta": 0.5,
                "za_bias": 0.0,
                "decay_rate": 0.01,
                "cooldown_threshold": 0.7,
                "desens_threshold_ticks": 3,
                "desens_rate": 0.05,
                "target_dd": 0.15,
                "target_sharpe": 1.5,
                "beta_temper": 0.5,
                "phase_threshold": 0.7,
                "phase_kappa": 2.0,
                "burst_factor": 0.35,
                "mod_t_max": 10.0,
                "mod_t_half": 5.0,
                "mod_k": 0.5,
                "max_desens_counter": 10,
                "desens_gain": 0.8,
            },
            "serotonin_legacy": {
                "tonic_beta": 0.35,
                "phasic_beta": 0.55,
                "stress_gain": 1.0,
                "drawdown_gain": 1.2,
                "novelty_gain": 0.6,
                "stress_threshold": 0.7,
                "release_threshold": 0.4,
                "hysteresis": 0.1,
                "cooldown_ticks": 3,
                "chronic_window": 6,
                "desensitization_rate": 0.05,
                "desensitization_decay": 0.05,
                "max_desensitization": 0.6,
                "floor_min": 0.1,
                "floor_max": 0.6,
                "floor_gain": 0.8,
                "cooldown_extension": 2,
            },
        }
        envelope = SerotoninConfigEnvelope.model_validate(config)
        assert envelope.active_profile == "v24"
        cfg, profile = envelope.get_active_config()
        assert profile == "v24"
        assert isinstance(cfg, SerotoninConfig)

    def test_rejects_invalid_profile_name(self):
        """Test that invalid profile names are rejected."""
        config = {
            "active_profile": "invalid",
            "serotonin_v24": {},
        }
        with pytest.raises(ValidationError):
            SerotoninConfigEnvelope.model_validate(config)

    def test_rejects_unknown_root_keys(self):
        """Test that unknown root keys are rejected by strict schema."""
        config = {
            "active_profile": "v24",
            "serotonin_v24": {},
            "unknown_key": "value",
        }
        with pytest.raises(ValidationError):
            SerotoninConfigEnvelope.model_validate(config)

    def test_get_active_config_missing_v24_section(self):
        """Test error when v24 profile is active but section is missing."""
        envelope = SerotoninConfigEnvelope(
            active_profile="v24",
            serotonin_v24=None,
            serotonin_legacy=None,
        )
        with pytest.raises(ValueError, match="serotonin_v24 section is missing"):
            envelope.get_active_config()

    def test_get_active_config_missing_legacy_section(self):
        """Test error when legacy profile is active but section is missing."""
        envelope = SerotoninConfigEnvelope(
            active_profile="legacy",
            serotonin_v24=None,
            serotonin_legacy=None,
        )
        with pytest.raises(ValueError, match="serotonin_legacy section is missing"):
            envelope.get_active_config()


class TestSerotoninConfigContract:
    """Tests for config contract loading and validation."""

    def test_save_and_reload_config_roundtrip(self, tmp_path):
        """Test saving and reloading config preserves schema without derived keys."""
        config = {
            "active_profile": "v24",
            "serotonin_v24": {
                "alpha": 0.5,
                "beta": 0.3,
                "gamma": 0.4,
                "delta_rho": 0.2,
                "k": 1.5,
                "theta": 0.0,
                "delta": 0.5,
                "za_bias": 0.0,
                "decay_rate": 0.01,
                "cooldown_threshold": 0.7,
                "desens_threshold_ticks": 3,
                "desens_rate": 0.05,
                "target_dd": 0.15,
                "target_sharpe": 1.5,
                "beta_temper": 0.5,
                "phase_threshold": 0.7,
                "phase_kappa": 2.0,
                "burst_factor": 0.35,
                "mod_t_max": 10.0,
                "mod_t_half": 5.0,
                "mod_k": 0.5,
                "max_desens_counter": 10,
                "desens_gain": 0.8,
                "gate_veto": 0.9,
                "phasic_veto": 1.0,
                "temperature_floor_min": 0.1,
                "temperature_floor_max": 0.6,
                "hysteresis_margin": 0.05,
            },
        }
        config_path = tmp_path / "serotonin.yaml"
        config_path.write_text(yaml.safe_dump(config))

        controller = SerotoninController(str(config_path))
        controller.save_config_to_yaml()

        saved = yaml.safe_load(config_path.read_text())
        assert saved["active_profile"] == "v24"
        assert "serotonin_v24" in saved
        assert "floor_min" not in saved["serotonin_v24"]
        assert "floor_max" not in saved["serotonin_v24"]

        reloaded = SerotoninController(str(config_path))
        assert reloaded.config["alpha"] == pytest.approx(0.5)

    def test_load_production_config(self):
        """Test loading the production serotonin.yaml config file."""
        config_path = Path(__file__).parents[4] / "configs" / "serotonin.yaml"
        if not config_path.exists():
            pytest.skip("Production config not found")

        controller = SerotoninController(str(config_path))
        assert controller._active_profile in ("v24", "legacy")
        assert controller.config is not None

    def test_legacy_profile_converts_to_v24(self, tmp_path):
        """Test that legacy config is converted to v24 format at runtime."""
        config = {
            "active_profile": "legacy",
            "serotonin_legacy": {
                "tonic_beta": 0.35,
                "phasic_beta": 0.55,
                "stress_gain": 1.0,
                "drawdown_gain": 1.2,
                "novelty_gain": 0.6,
                "stress_threshold": 0.7,
                "release_threshold": 0.4,
                "hysteresis": 0.1,
                "cooldown_ticks": 3,
                "chronic_window": 6,
                "desensitization_rate": 0.05,
                "desensitization_decay": 0.05,
                "max_desensitization": 0.6,
                "floor_min": 0.1,
                "floor_max": 0.6,
                "floor_gain": 0.8,
                "cooldown_extension": 2,
            },
        }
        config_path = tmp_path / "serotonin.yaml"
        config_path.write_text(yaml.safe_dump(config))

        controller = SerotoninController(str(config_path))
        assert controller._active_profile == "legacy"
        # Verify config was converted to v24 format
        assert "alpha" in controller.config
        assert "cooldown_threshold" in controller.config

    def test_legacy_max_desens_counter_bounded(self, tmp_path):
        """Test that legacy config conversion bounds max_desens_counter."""
        config = {
            "active_profile": "legacy",
            "serotonin_legacy": {
                "tonic_beta": 0.35,
                "phasic_beta": 0.55,
                "stress_gain": 1.0,
                "drawdown_gain": 1.2,
                "novelty_gain": 0.6,
                "stress_threshold": 0.7,
                "release_threshold": 0.4,
                "hysteresis": 0.1,
                "cooldown_ticks": 3,
                "chronic_window": 6,
                "desensitization_rate": 0.001,  # Very small rate
                "desensitization_decay": 0.05,
                "max_desensitization": 0.99,  # Near max
                "floor_min": 0.1,
                "floor_max": 0.6,
                "floor_gain": 0.8,
                "cooldown_extension": 2,
            },
        }
        config_path = tmp_path / "serotonin.yaml"
        config_path.write_text(yaml.safe_dump(config))

        controller = SerotoninController(str(config_path))
        # Without bounds, this would be 990/0.01 = 99000
        # With bounds, it should be capped at 10000
        assert controller.config["max_desens_counter"] <= 10000
        assert controller.config["max_desens_counter"] >= 1

    def test_config_file_not_found(self, tmp_path):
        """Test error handling for missing config file."""
        with pytest.raises(FileNotFoundError):
            SerotoninController(str(tmp_path / "nonexistent.yaml"))

    def test_invalid_yaml_structure(self, tmp_path):
        """Test error handling for invalid YAML structure."""
        config_path = tmp_path / "invalid.yaml"
        config_path.write_text("not_a_mapping")

        with pytest.raises(ValueError, match="must be a mapping"):
            SerotoninController(str(config_path))


class TestSerotoninLegacyConfig:
    """Tests for SerotoninLegacyConfig validation."""

    def test_valid_legacy_config(self):
        """Test valid legacy config validation."""
        config = SerotoninLegacyConfig(
            tonic_beta=0.35,
            phasic_beta=0.55,
            stress_gain=1.0,
            drawdown_gain=1.2,
            novelty_gain=0.6,
            stress_threshold=0.7,
            release_threshold=0.4,
            hysteresis=0.1,
            cooldown_ticks=3,
            chronic_window=6,
            desensitization_rate=0.05,
            desensitization_decay=0.05,
            max_desensitization=0.6,
            floor_min=0.1,
            floor_max=0.6,
            floor_gain=0.8,
            cooldown_extension=2,
        )
        assert config.tonic_beta == 0.35

    def test_rejects_out_of_range_values(self):
        """Test that out-of-range values are rejected."""
        with pytest.raises(ValidationError):
            SerotoninLegacyConfig(
                tonic_beta=1.5,  # Out of range: should be <= 1.0
                phasic_beta=0.55,
                stress_gain=1.0,
                drawdown_gain=1.2,
                novelty_gain=0.6,
                stress_threshold=0.7,
                release_threshold=0.4,
                hysteresis=0.1,
                cooldown_ticks=3,
                chronic_window=6,
                desensitization_rate=0.05,
                desensitization_decay=0.05,
                max_desensitization=0.6,
                floor_min=0.1,
                floor_max=0.6,
                floor_gain=0.8,
                cooldown_extension=2,
            )
