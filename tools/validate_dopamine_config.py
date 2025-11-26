#!/usr/bin/env python3
"""Validate dopamine configuration against JSON schema.

Usage:
    python tools/validate_dopamine_config.py <config.yaml>
    python tools/validate_dopamine_config.py --all  # Validate all configs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    import jsonschema  # noqa: F401 - required for Draft7Validator
    from jsonschema import Draft7Validator
except ImportError:
    print(
        "Error: jsonschema package required. Install with: pip install jsonschema",
        file=sys.stderr,
    )
    sys.exit(1)


def load_schema(schema_path: Path) -> dict[str, Any]:
    """Load JSON schema."""
    with open(schema_path, "r") as f:
        return json.load(f)


def load_config(config_path: Path) -> dict[str, Any]:
    """Load YAML config."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def validate_config(
    config: dict[str, Any], schema: dict[str, Any]
) -> tuple[bool, list[str]]:
    """Validate config against schema.

    Returns:
        (is_valid, error_messages)
    """
    validator = Draft7Validator(schema)
    errors = []

    for error in validator.iter_errors(config):
        # Format error message
        path = ".".join(str(p) for p in error.path) if error.path else "root"
        errors.append(f"{path}: {error.message}")

    return len(errors) == 0, errors


def validate_semantic_rules(config: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate semantic rules not covered by JSON schema.

    These are constraints that require comparing multiple fields.
    """
    errors = []

    # Check: min_temperature <= base_temperature
    if "min_temperature" in config and "base_temperature" in config:
        if config["min_temperature"] > config["base_temperature"]:
            errors.append("min_temperature must be <= base_temperature")

    # Check: temp_adapt_min_base <= temp_adapt_max_base
    if "temp_adapt_min_base" in config and "temp_adapt_max_base" in config:
        if config["temp_adapt_min_base"] > config["temp_adapt_max_base"]:
            errors.append("temp_adapt_min_base must be <= temp_adapt_max_base")

    # Check: ddm_min_temperature_scale <= ddm_max_temperature_scale
    if "ddm_min_temperature_scale" in config and "ddm_max_temperature_scale" in config:
        if config["ddm_min_temperature_scale"] > config["ddm_max_temperature_scale"]:
            errors.append(
                "ddm_min_temperature_scale must be <= ddm_max_temperature_scale"
            )

    # Note: go >= hold >= no_go is enforced at runtime by check_monotonic_thresholds
    # We document but don't validate here since it's a soft constraint

    return len(errors) == 0, errors


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate dopamine configuration")
    parser.add_argument(
        "config",
        type=Path,
        nargs="?",
        help="Config file to validate",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate all dopamine configs (main + profiles)",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default="schemas/dopamine.schema.json",
        help="Schema file path",
    )

    args = parser.parse_args()

    if not args.all and not args.config:
        parser.error("Either provide a config file or use --all")
        return 1

    # Load schema
    if not args.schema.exists():
        print(f"Error: Schema file not found: {args.schema}", file=sys.stderr)
        return 1

    schema = load_schema(args.schema)

    # Determine configs to validate
    if args.all:
        configs = [
            Path("config/dopamine.yaml"),
            Path("config/profiles/conservative.yaml"),
            Path("config/profiles/normal.yaml"),
            Path("config/profiles/aggressive.yaml"),
        ]
    else:
        configs = [args.config]

    # Validate each config
    all_valid = True
    for config_path in configs:
        if not config_path.exists():
            print(f"⚠️  Config not found: {config_path}")
            continue

        print(f"\nValidating: {config_path}")
        print("-" * 60)

        try:
            config = load_config(config_path)
        except Exception as e:
            print(f"❌ Failed to load config: {e}")
            all_valid = False
            continue

        # JSON schema validation
        is_valid, errors = validate_config(config, schema)

        if not is_valid:
            print("❌ Schema validation failed:")
            for error in errors:
                print(f"  • {error}")
            all_valid = False
        else:
            print("✅ Schema validation passed")

        # Semantic validation
        is_valid_sem, errors_sem = validate_semantic_rules(config)

        if not is_valid_sem:
            print("❌ Semantic validation failed:")
            for error in errors_sem:
                print(f"  • {error}")
            all_valid = False
        else:
            print("✅ Semantic validation passed")

    print()
    if all_valid:
        print("✅ All configurations valid")
        return 0
    else:
        print("❌ Some configurations invalid")
        return 1


if __name__ == "__main__":
    sys.exit(main())
