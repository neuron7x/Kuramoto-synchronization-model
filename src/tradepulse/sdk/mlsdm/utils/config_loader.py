"""Configuration loading utilities for MLSDM.

This module provides utilities for loading YAML configuration files
and converting them to the appropriate format for MemoryManager.
"""

from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Utility class for loading MLSDM configurations from YAML files."""

    @staticmethod
    def load_config(path: str | Path) -> Dict[str, Any]:
        """Load configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            Configuration dictionary suitable for MemoryManager.

        Raises:
            FileNotFoundError: If the configuration file doesn't exist.
            yaml.YAMLError: If the YAML file is malformed.
        """
        config_path = Path(path)

        if not config_path.exists():
            msg = f"Configuration file not found: {config_path}"
            logger.error(msg)
            raise FileNotFoundError(msg)

        logger.info(f"Loading configuration from: {config_path}")

        try:
            with config_path.open("r") as f:
                config = yaml.safe_load(f)

            if config is None:
                config = {}

            logger.info("Configuration loaded successfully")
            return config

        except yaml.YAMLError as e:
            msg = f"Failed to parse YAML configuration: {e}"
            logger.error(msg)
            raise

    @staticmethod
    def _set_nested(target: Dict[str, Any], keys: List[str], value: Any) -> None:
        """Assign a value into a nested dictionary using a list of keys."""

        current = target
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value

    @staticmethod
    def _collect_env_overrides(env_prefix: str) -> Dict[str, Any]:
        """Collect environment-based overrides using double-underscore paths.

        Example:
            MLSDM_AGENT__STATE_DIM=16 -> {"agent": {"state_dim": 16}}
        """

        overrides: Dict[str, Any] = {}
        if not env_prefix:
            return overrides

        for key, raw_value in os.environ.items():
            if not key.startswith(env_prefix):
                continue
            path = key[len(env_prefix) :].split("__")
            path = [segment.lower() for segment in path if segment]
            if not path:
                continue
            try:
                value = yaml.safe_load(raw_value)
            except yaml.YAMLError:
                value = raw_value
            ConfigLoader._set_nested(overrides, path, value)
        return overrides

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries.

        Args:
            base: Base dictionary with default values.
            override: Dictionary with override values.

        Returns:
            Merged dictionary where override takes precedence.
        """
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigLoader._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @staticmethod
    def load_config_with_defaults(
        path: str | Path, defaults: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Load configuration and merge with defaults.

        Args:
            path: Path to the YAML configuration file.
            defaults: Optional default values to use as fallback.

        Returns:
            Merged configuration dictionary.
        """
        return ConfigLoader.load_config_layered(path, defaults=defaults)

    @staticmethod
    def load_config_layered(
        path: str | Path,
        defaults: Dict[str, Any] | None = None,
        env_prefix: str = "MLSDM_",
        cli_overrides: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Load configuration with deterministic precedence.

        Precedence: CLI overrides > environment overrides > YAML file > defaults.
        """

        base_config: Dict[str, Any] = copy.deepcopy(defaults) if defaults else {}

        yaml_config = ConfigLoader.load_config(path)
        merged = ConfigLoader._deep_merge(base_config, yaml_config)

        env_overrides = ConfigLoader._collect_env_overrides(env_prefix)
        if env_overrides:
            merged = ConfigLoader._deep_merge(merged, env_overrides)

        if cli_overrides:
            merged = ConfigLoader._deep_merge(merged, cli_overrides)

        return merged
