#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Migration tool for dopamine configuration versions.

Usage:
    python tools/migrate_dopamine_config.py <input_config.yaml> [output_config.yaml]

If output is not specified, prints to stdout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

import yaml


def migrate_2_2_to_1_0(config: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate from version 2.2.x to 1.0.0.

    Version 1.0.0 is the new production schema with standardized naming
    and additional safety parameters.
    """
    migrated = config.copy()

    # Update version
    migrated["version"] = "1.0.0"

    # Ensure all required fields exist with safe defaults if missing
    defaults = {
        "rpe_ema_beta": 0.2,
        "temp_adapt_target_var": 0.12,
        "temp_adapt_lr": 0.05,
        "temp_adapt_beta1": 0.9,
        "temp_adapt_beta2": 0.999,
        "temp_adapt_epsilon": 1.0e-8,
        "temp_adapt_min_base": 0.2,
        "temp_adapt_max_base": 2.5,
        "rpe_var_release_threshold": 0.35,
        "rpe_var_release_hysteresis": 0.05,
        "ddm_temp_gain": 0.4,
        "ddm_threshold_gain": 0.3,
        "ddm_hold_gain": 0.6,
        "ddm_min_temperature_scale": 0.5,
        "ddm_max_temperature_scale": 2.0,
        "ddm_baseline_a": 1.0,
        "ddm_baseline_t0": 0.2,
        "ddm_eps": 1.0e-6,
        "hold_threshold": 0.4,
    }

    for key, default_value in defaults.items():
        if key not in migrated:
            migrated[key] = default_value

    return migrated


def detect_version(config: Dict[str, Any]) -> str:
    """Detect configuration version."""
    version_str = config.get("version", "unknown")
    if isinstance(version_str, str):
        return version_str
    return str(version_str)


def migrate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate configuration to latest version (1.0.0)."""
    version = detect_version(config)

    if version.startswith("2.2"):
        return migrate_2_2_to_1_0(config)
    elif version.startswith("1.0"):
        # Already at target version
        return config
    else:
        raise ValueError(f"Unknown configuration version: {version}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrate dopamine configuration to latest version")
    parser.add_argument(
        "input",
        type=Path,
        help="Input configuration file (YAML)",
    )
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Output configuration file (YAML). If not specified, prints to stdout.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing output",
    )

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    # Load input config
    with open(args.input, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        print("Error: Configuration must be a YAML mapping/dict", file=sys.stderr)
        return 1

    original_version = detect_version(config)
    print(f"Input version: {original_version}", file=sys.stderr)

    # Migrate
    try:
        migrated = migrate_config(config)
    except Exception as e:
        print(f"Error during migration: {e}", file=sys.stderr)
        return 1

    migrated_version = detect_version(migrated)
    print(f"Output version: {migrated_version}", file=sys.stderr)

    # Output
    output_yaml = yaml.dump(
        migrated,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )

    if args.dry_run:
        print("\n--- Dry run (no files written) ---", file=sys.stderr)
        print(output_yaml)
        return 0

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_yaml)
        print(f"Migrated configuration written to: {args.output}", file=sys.stderr)
    else:
        print(output_yaml)

    return 0


if __name__ == "__main__":
    sys.exit(main())
