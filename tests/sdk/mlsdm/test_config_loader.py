"""Tests for ConfigLoader utility."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tradepulse.sdk.mlsdm.utils.config_loader import ConfigLoader


class TestConfigLoader:
    """Tests for ConfigLoader class."""

    def test_load_config_success(self, tmp_path: Path) -> None:
        """Test successful config loading."""
        config_data = {
            "fhmc": {
                "alpha_target": [0.5, 1.5],
                "orexin": {"k1": 1.0, "k2": 0.7},
            },
            "agent": {
                "state_dim": 8,
                "action_dim": 2,
            },
        }

        config_file = tmp_path / "config.yaml"
        with config_file.open("w") as f:
            yaml.dump(config_data, f)

        result = ConfigLoader.load_config(config_file)

        assert result["fhmc"]["alpha_target"] == [0.5, 1.5]
        assert result["fhmc"]["orexin"]["k1"] == 1.0
        assert result["agent"]["state_dim"] == 8

    def test_load_config_file_not_found(self, tmp_path: Path) -> None:
        """Test loading non-existent config file."""
        config_file = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError) as exc_info:
            ConfigLoader.load_config(config_file)

        assert "Configuration file not found" in str(exc_info.value)

    def test_load_config_empty_file(self, tmp_path: Path) -> None:
        """Test loading empty config file."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        result = ConfigLoader.load_config(config_file)

        assert result == {}

    def test_load_config_malformed_yaml(self, tmp_path: Path) -> None:
        """Test loading malformed YAML file."""
        config_file = tmp_path / "malformed.yaml"
        config_file.write_text("invalid: yaml: content:\n  - unclosed [bracket")

        with pytest.raises(yaml.YAMLError):
            ConfigLoader.load_config(config_file)

    def test_load_config_with_defaults(self, tmp_path: Path) -> None:
        """Test loading config with defaults."""
        config_data = {"fhmc": {"alpha_target": [0.5, 1.5]}}

        config_file = tmp_path / "config.yaml"
        with config_file.open("w") as f:
            yaml.dump(config_data, f)

        defaults = {
            "agent": {"state_dim": 10, "action_dim": 3},
            "optimizer": {"dim": 5},
        }

        result = ConfigLoader.load_config_with_defaults(config_file, defaults)

        # Config values should take precedence
        assert result["fhmc"]["alpha_target"] == [0.5, 1.5]
        # Default values should be present
        assert result["agent"]["state_dim"] == 10
        assert result["optimizer"]["dim"] == 5

    def test_load_config_with_defaults_override(self, tmp_path: Path) -> None:
        """Test that config overrides defaults."""
        config_data = {
            "fhmc": {"alpha_target": [0.5, 1.5]},
            "agent": {"state_dim": 20},  # Should override default
        }

        config_file = tmp_path / "config.yaml"
        with config_file.open("w") as f:
            yaml.dump(config_data, f)

        defaults = {
            "agent": {"state_dim": 10, "action_dim": 3},
        }

        result = ConfigLoader.load_config_with_defaults(config_file, defaults)

        # Config should override default
        assert result["agent"]["state_dim"] == 20
        # Other default values should still be present
        assert result["agent"]["action_dim"] == 3

    def test_load_config_path_as_string(self, tmp_path: Path) -> None:
        """Test loading config with path as string."""
        config_data = {"test": "value"}

        config_file = tmp_path / "config.yaml"
        with config_file.open("w") as f:
            yaml.dump(config_data, f)

        result = ConfigLoader.load_config(str(config_file))

        assert result["test"] == "value"

    def test_env_overrides_yaml_and_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ensure environment variables take precedence over YAML and defaults."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump({"agent": {"state_dim": 8, "action_dim": 2}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("MLSDM__AGENT__STATE_DIM", "16")

        result = ConfigLoader.load_config_with_defaults(
            config_file, defaults={"agent": {"state_dim": 4, "action_dim": 3}}
        )

        assert result["agent"]["state_dim"] == 16
        assert result["agent"]["action_dim"] == 2

    def test_cli_overrides_win_over_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ensure explicit CLI overrides outrank environment overrides."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump({"agent": {"state_dim": 8, "action_dim": 2}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("MLSDM__AGENT__STATE_DIM", "12")

        result = ConfigLoader.load_config_with_defaults(
            config_file,
            defaults={"agent": {"state_dim": 4, "action_dim": 3}},
            overrides={"agent.state_dim": 20},
        )

        assert result["agent"]["state_dim"] == 20
        assert result["agent"]["action_dim"] == 2
