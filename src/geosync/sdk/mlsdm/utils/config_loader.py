# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Configuration loading utilities for MLSDM.

This module provides utilities for loading YAML configuration files
and converting them to the appropriate format for MemoryManager.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable

import yaml

logger = logging.getLogger(__name__)

ENV_PREFIX = "MLSDM__"


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
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigLoader._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @staticmethod
    def load_config_with_defaults(
        path: str | Path,
        defaults: Dict[str, Any] | None = None,
        *,
        env_prefix: str = ENV_PREFIX,
        overrides: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Load configuration and merge with defaults.

        Args:
            path: Path to the YAML configuration file.
            defaults: Optional default values to use as fallback.
            env_prefix: Environment variable prefix used for overrides.
            overrides: Explicit CLI-style overrides applied at highest precedence.

        Returns:
            Merged configuration dictionary.
        """
        config = ConfigLoader.load_config(path)
        merged: Dict[str, Any] = (defaults or {}).copy()
        merged = ConfigLoader._deep_merge(merged, config)
        merged = ConfigLoader._apply_env_overrides(merged, env_prefix)
        merged = ConfigLoader._apply_cli_overrides(merged, overrides or {})
        return merged

    @staticmethod
    def _apply_env_overrides(config: Dict[str, Any], prefix: str = ENV_PREFIX) -> Dict[str, Any]:
        """Apply environment variable overrides using a prefix-scoped, nested syntax.

        Segments are normalized to lowercase to match YAML keys.
        """

        def iter_env() -> Iterable[tuple[list[str], Any]]:
            for key, value in os.environ.items():
                if not key.startswith(prefix):
                    continue
                remainder = key[len(prefix) :]
                if not remainder:
                    continue
                path = ConfigLoader._normalize_path(remainder.split("__"))
                if not path:
                    continue
                parsed_value = ConfigLoader._parse_override_value(value, source=key)
                yield [segment.lower() for segment in path], parsed_value

        merged = config.copy()
        for path, value in iter_env():
            ConfigLoader._set_nested(merged, path, value)
        return merged

    @staticmethod
    def _apply_cli_overrides(config: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Apply explicit CLI overrides expressed in dotted or '__' notation."""
        merged = config.copy()
        for raw_path, value in overrides.items():
            if not raw_path:
                continue
            path = [segment for segment in raw_path.replace("__", ".").split(".") if segment]
            path = ConfigLoader._normalize_path(path)
            if not path:
                continue
            ConfigLoader._set_nested(merged, path, value)
        return merged

    @staticmethod
    def _normalize_path(path: Iterable[str]) -> list[str]:
        return [segment.lower() for segment in path if segment]

    @staticmethod
    def _parse_override_value(value: str, *, source: str) -> Any:
        """Parse an override value with light heuristics before YAML parsing."""
        for caster in (int, float):
            try:
                return caster(value)
            except ValueError:
                pass
        lowered = value.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            return yaml.safe_load(value)
        except yaml.YAMLError:
            logger.warning("Failed to parse override %s; using raw string", source)
            return value

    @staticmethod
    def _set_nested(config: Dict[str, Any], path: list[str], value: Any) -> None:
        if not path:
            return
        cursor = config
        for segment in path[:-1]:
            if segment not in cursor or not isinstance(cursor[segment], dict):
                cursor[segment] = {}
            cursor = cursor[segment]
        cursor[path[-1]] = value
