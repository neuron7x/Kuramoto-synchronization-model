"""Configuration loading utilities for MLSDM.

This module provides utilities for loading YAML configuration files
and converting them to the appropriate format for MemoryManager.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

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
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
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
        config = ConfigLoader.load_config(path)

        if defaults:
            # Deep merge defaults with loaded config (config takes precedence)
            merged = ConfigLoader._deep_merge(defaults, config)
            return merged

        return config
