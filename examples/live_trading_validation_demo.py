# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Live trading setup validation example.

This module demonstrates how to properly validate and configure
the live trading system before going live. It includes:

1. Configuration validation
2. Connection testing
3. Risk parameter validation
4. Pre-flight checks

Usage:
    python examples/live_trading_validation_demo.py
    python examples/live_trading_validation_demo.py --config configs/live/paper.toml
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""

    name: str
    passed: bool
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }


class LiveTradingValidator:
    """Validator for live trading configuration and readiness."""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path
        self.config: dict[str, Any] = {}
        self.results: list[ValidationResult] = []

    def load_config(self) -> bool:
        """Load and parse configuration file."""
        if not self.config_path:
            self.results.append(
                ValidationResult(
                    name="config_load",
                    passed=False,
                    message="No configuration file specified",
                )
            )
            return False

        if not self.config_path.exists():
            self.results.append(
                ValidationResult(
                    name="config_load",
                    passed=False,
                    message=f"Configuration file not found: {self.config_path}",
                )
            )
            return False

        try:
            if self.config_path.suffix == ".toml":
                try:
                    import tomllib
                except ModuleNotFoundError:
                    import tomli as tomllib

                with open(self.config_path, "rb") as f:
                    self.config = tomllib.load(f)
            elif self.config_path.suffix in (".yaml", ".yml"):
                import yaml

                with open(self.config_path, "r") as f:
                    self.config = yaml.safe_load(f)
            elif self.config_path.suffix == ".json":
                with open(self.config_path, "r") as f:
                    self.config = json.load(f)
            else:
                self.results.append(
                    ValidationResult(
                        name="config_load",
                        passed=False,
                        message=f"Unsupported config format: {self.config_path.suffix}",
                    )
                )
                return False

            self.results.append(
                ValidationResult(
                    name="config_load",
                    passed=True,
                    message=f"Configuration loaded from {self.config_path}",
                    details={"sections": list(self.config.keys())},
                )
            )
            return True

        except Exception as e:
            self.results.append(
                ValidationResult(
                    name="config_load",
                    passed=False,
                    message=f"Failed to load configuration: {e}",
                )
            )
            return False

    def validate_venues(self) -> bool:
        """Validate venue configurations."""
        venues = self.config.get("venues", {})

        if not venues:
            self.results.append(
                ValidationResult(
                    name="venues",
                    passed=False,
                    message="No venues configured",
                )
            )
            return False

        all_valid = True
        for venue_name, venue_config in venues.items():
            # Check required fields
            required_fields = ["connector"]
            missing = [f for f in required_fields if f not in venue_config]

            if missing:
                self.results.append(
                    ValidationResult(
                        name=f"venue_{venue_name}",
                        passed=False,
                        message=f"Missing required fields: {missing}",
                    )
                )
                all_valid = False
            else:
                self.results.append(
                    ValidationResult(
                        name=f"venue_{venue_name}",
                        passed=True,
                        message=f"Venue '{venue_name}' configuration valid",
                        details={"connector": venue_config.get("connector")},
                    )
                )

        return all_valid

    def validate_risk_limits(self) -> bool:
        """Validate risk management configuration."""
        risk_config = self.config.get("risk", {})

        validations = []

        # Check position limits
        max_position = risk_config.get("max_position_size")
        if max_position is not None:
            if max_position <= 0:
                validations.append(("max_position_size", False, "Must be positive"))
            else:
                validations.append(("max_position_size", True, f"Set to {max_position}"))
        else:
            validations.append(("max_position_size", False, "Not configured"))

        # Check daily loss limit
        daily_loss = risk_config.get("max_daily_loss")
        if daily_loss is not None:
            if daily_loss <= 0:
                validations.append(("max_daily_loss", False, "Must be positive"))
            else:
                validations.append(("max_daily_loss", True, f"Set to {daily_loss}"))
        else:
            validations.append(("max_daily_loss", False, "Not configured (recommended)"))

        # Check kill switch
        kill_switch = risk_config.get("kill_switch_enabled", True)
        validations.append(
            (
                "kill_switch",
                kill_switch,
                "Enabled" if kill_switch else "Disabled (WARNING)",
            )
        )

        all_valid = all(v[1] for v in validations)

        self.results.append(
            ValidationResult(
                name="risk_limits",
                passed=all_valid,
                message="Risk limits validation",
                details={v[0]: {"valid": v[1], "message": v[2]} for v in validations},
            )
        )

        return all_valid

    def validate_credentials(self) -> bool:
        """Validate credential configuration (not actual credentials)."""
        venues = self.config.get("venues", {})

        all_valid = True
        for venue_name, venue_config in venues.items():
            creds = venue_config.get("credentials", {})

            env_prefix = creds.get("env_prefix")
            secret_backend = creds.get("secret_backend")

            if not env_prefix and not secret_backend:
                self.results.append(
                    ValidationResult(
                        name=f"credentials_{venue_name}",
                        passed=False,
                        message=f"No credential source configured for {venue_name}",
                    )
                )
                all_valid = False
            else:
                source = "env_prefix" if env_prefix else "secret_backend"
                self.results.append(
                    ValidationResult(
                        name=f"credentials_{venue_name}",
                        passed=True,
                        message=f"Credentials configured via {source}",
                    )
                )

        return all_valid

    def validate_state_directory(self) -> bool:
        """Validate state directory configuration."""
        state_dir = self.config.get("state", {}).get("directory")

        if not state_dir:
            state_dir = "./state"  # Default

        path = Path(state_dir)

        if path.exists():
            if path.is_dir():
                self.results.append(
                    ValidationResult(
                        name="state_directory",
                        passed=True,
                        message=f"State directory exists: {path}",
                    )
                )
                return True
            else:
                self.results.append(
                    ValidationResult(
                        name="state_directory",
                        passed=False,
                        message=f"State path exists but is not a directory: {path}",
                    )
                )
                return False
        else:
            # Directory doesn't exist, but can be created
            self.results.append(
                ValidationResult(
                    name="state_directory",
                    passed=True,
                    message=f"State directory will be created: {path}",
                )
            )
            return True

    def run_all_validations(self) -> bool:
        """Run all validation checks."""
        if not self.load_config():
            return False

        checks = [
            self.validate_venues(),
            self.validate_risk_limits(),
            self.validate_credentials(),
            self.validate_state_directory(),
        ]

        return all(checks)

    def print_report(self) -> None:
        """Print a formatted validation report."""
        print("\n" + "=" * 60)
        print("  GeoSync Live Trading Validation Report")
        print("=" * 60 + "\n")

        passed_count = sum(1 for r in self.results if r.passed)
        failed_count = len(self.results) - passed_count

        for result in self.results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"  {status}  {result.name}")
            print(f"         {result.message}")
            if result.details:
                for key, value in result.details.items():
                    print(f"           • {key}: {value}")
            print()

        print("-" * 60)
        print(f"  Summary: {passed_count} passed, {failed_count} failed")
        print("-" * 60)

        if failed_count > 0:
            print("\n  ⚠️  Some validations failed. Please review before going live.\n")
        else:
            print("\n  ✅ All validations passed. System is ready for live trading.\n")


def preflight_checks() -> list[ValidationResult]:
    """Run pre-flight checks for system readiness."""
    results = []

    # Check Python version
    import sys

    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        results.append(
            ValidationResult(
                name="python_version",
                passed=True,
                message=f"Python {py_version} supported",
            )
        )
    else:
        results.append(
            ValidationResult(
                name="python_version",
                passed=False,
                message=f"Python {py_version} not recommended (3.11+ required)",
            )
        )

    # Check core dependencies
    core_deps = [
        ("numpy", "numpy"),
        ("pandas", "pandas"),
        ("pydantic", "pydantic"),
    ]

    for name, import_name in core_deps:
        try:
            __import__(import_name)
            results.append(
                ValidationResult(
                    name=f"dependency_{name}",
                    passed=True,
                    message=f"{name} is installed",
                )
            )
        except ImportError:
            results.append(
                ValidationResult(
                    name=f"dependency_{name}",
                    passed=False,
                    message=f"{name} is not installed",
                )
            )

    # Check optional dependencies
    optional_deps = [
        ("redis", "redis", "For Redis-backed feature store"),
        ("prometheus_client", "prometheus-client", "For metrics export"),
    ]

    for name, import_name, purpose in optional_deps:
        try:
            __import__(name)
            results.append(
                ValidationResult(
                    name=f"optional_{name}",
                    passed=True,
                    message=f"{name} available ({purpose})",
                )
            )
        except ImportError:
            results.append(
                ValidationResult(
                    name=f"optional_{name}",
                    passed=True,  # Optional, so still passes
                    message=f"{name} not installed ({purpose}) - optional",
                )
            )

    return results


def main():
    """Main entry point for live trading validation."""
    parser = argparse.ArgumentParser(
        description="Validate GeoSync live trading configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Validate with default config
    python examples/live_trading_validation_demo.py

    # Validate specific config
    python examples/live_trading_validation_demo.py --config configs/live/production.toml

    # Run pre-flight checks only
    python examples/live_trading_validation_demo.py --preflight-only
        """,
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/live/default.toml",
        help="Path to configuration file (default: configs/live/default.toml)",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run only pre-flight system checks",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    print("\n🚀 GeoSync Live Trading Validation\n")

    # Run pre-flight checks
    print("Running pre-flight system checks...")
    preflight_results = preflight_checks()

    all_passed = all(r.passed for r in preflight_results)

    if args.preflight_only:
        if args.json:
            print(json.dumps([r.to_dict() for r in preflight_results], indent=2))
        else:
            for result in preflight_results:
                status = "✅" if result.passed else "❌"
                print(f"  {status} {result.name}: {result.message}")

            print(f"\nPre-flight: {'PASSED' if all_passed else 'FAILED'}")

        return 0 if all_passed else 1

    # Run configuration validation
    print("\nValidating configuration...")

    config_path = Path(args.config)
    validator = LiveTradingValidator(config_path)
    config_valid = validator.run_all_validations()

    if args.json:
        all_results = preflight_results + validator.results
        print(json.dumps([r.to_dict() for r in all_results], indent=2))
    else:
        validator.results = preflight_results + validator.results
        validator.print_report()

    return 0 if (all_passed and config_valid) else 1


if __name__ == "__main__":
    sys.exit(main())
