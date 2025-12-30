#!/usr/bin/env python3
"""Calibration utility for TradePulse controllers and modules.

This script provides an interactive interface to calibrate accuracy, thresholds,
and sensitivity parameters across all TradePulse controllers and modules.

Usage:
    python scripts/calibrate_controllers.py --controller nak --profile balanced
    python scripts/calibrate_controllers.py --controller dopamine --profile aggressive
    python scripts/calibrate_controllers.py --list-profiles
    python scripts/calibrate_controllers.py --validate conf/nak/default.yaml
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import os
import yaml

# Import calibration_constants module
# Note: This script is intended to be run from the repository root
# For development, use: pip install -e .
try:
    os.environ.setdefault("TRADEPULSE_LIGHT_DATA_IMPORT", "1")
    from core.neuro.calibration_constants import (
        DopamineParameterRanges,
        NAKParameterRanges,
        RegimeAdaptiveParameterRanges,
        RiskEngineParameterRanges,
        SerotoninParameterRanges,
        validate_parameter_invariants,
    )
    from core.data.dataset_contracts import contract_by_path
    from core.data.fingerprint import record_run_fingerprint
except ImportError:
    # Fallback for when running directly from scripts directory
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.neuro.calibration_constants import (  # noqa: F401
        DopamineParameterRanges,
        NAKParameterRanges,
        RegimeAdaptiveParameterRanges,
        RiskEngineParameterRanges,
        SerotoninParameterRanges,
        validate_parameter_invariants,
    )
    from core.data.dataset_contracts import contract_by_path  # noqa: F401
    from core.data.fingerprint import record_run_fingerprint  # noqa: F401

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Calibration profiles for different market conditions
CALIBRATION_PROFILES = {
    "conservative": {
        "description": "Low risk, tight thresholds, minimal sensitivity",
        "nak": {
            "EI_low": 0.40,
            "EI_high": 0.70,
            "EI_crit": 0.20,
            "vol_amber": 0.60,
            "vol_red": 0.80,
            "dd_amber": 0.30,
            "dd_red": 0.60,
            "delta_r_limit": 0.15,
            "risk_mult": {"GREEN": 1.00, "AMBER": 0.60, "RED": 0.00},
            "activity_mult": {"GREEN": 1.10, "AMBER": 0.85, "RED": 0.50},
        },
        "dopamine": {
            "learning_rate_v": 0.05,
            "burst_factor": 1.5,
            "base_temperature": 0.8,
            "invigoration_threshold": 0.80,
            "no_go_threshold": 0.30,
        },
        "serotonin": {
            "stress_threshold": 0.70,
            "release_threshold": 0.45,
            "hysteresis": 0.15,
            "cooldown_ticks": 8,
            "stress_gain": 0.8,
        },
        "risk_engine": {
            "max_daily_loss_percent": 0.03,  # 3%
            "max_leverage": 3.0,
            "safe_mode_position_multiplier": 0.20,
            "kill_switch_loss_streak": 3,
        },
        "regime_adaptive": {
            "calm_threshold": 0.004,
            "stressed_threshold": 0.018,
            "critical_threshold": 0.035,
            "calm_multiplier": 1.05,
            "stressed_multiplier": 0.60,
            "critical_multiplier": 0.35,
        },
    },
    "balanced": {
        "description": "Moderate risk, standard thresholds, balanced sensitivity",
        "nak": {
            "EI_low": 0.35,
            "EI_high": 0.65,
            "EI_crit": 0.15,
            "vol_amber": 0.70,
            "vol_red": 0.90,
            "dd_amber": 0.40,
            "dd_red": 0.70,
            "delta_r_limit": 0.20,
            "risk_mult": {"GREEN": 1.00, "AMBER": 0.65, "RED": 0.00},
            "activity_mult": {"GREEN": 1.20, "AMBER": 0.90, "RED": 0.60},
        },
        "dopamine": {
            "learning_rate_v": 0.10,
            "burst_factor": 2.5,
            "base_temperature": 1.0,
            "invigoration_threshold": 0.75,
            "no_go_threshold": 0.25,
        },
        "serotonin": {
            "stress_threshold": 0.80,
            "release_threshold": 0.50,
            "hysteresis": 0.10,
            "cooldown_ticks": 5,
            "stress_gain": 1.0,
        },
        "risk_engine": {
            "max_daily_loss_percent": 0.05,  # 5%
            "max_leverage": 5.0,
            "safe_mode_position_multiplier": 0.25,
            "kill_switch_loss_streak": 5,
        },
        "regime_adaptive": {
            "calm_threshold": 0.005,
            "stressed_threshold": 0.020,
            "critical_threshold": 0.040,
            "calm_multiplier": 1.10,
            "stressed_multiplier": 0.65,
            "critical_multiplier": 0.40,
        },
    },
    "aggressive": {
        "description": "Higher risk, loose thresholds, high sensitivity",
        "nak": {
            "EI_low": 0.30,
            "EI_high": 0.60,
            "EI_crit": 0.10,
            "vol_amber": 0.80,
            "vol_red": 1.00,
            "dd_amber": 0.50,
            "dd_red": 0.80,
            "delta_r_limit": 0.25,
            "risk_mult": {"GREEN": 1.00, "AMBER": 0.75, "RED": 0.00},
            "activity_mult": {"GREEN": 1.30, "AMBER": 1.00, "RED": 0.70},
        },
        "dopamine": {
            "learning_rate_v": 0.15,
            "burst_factor": 3.5,
            "base_temperature": 1.5,
            "invigoration_threshold": 0.65,
            "no_go_threshold": 0.15,
        },
        "serotonin": {
            "stress_threshold": 0.90,
            "release_threshold": 0.55,
            "hysteresis": 0.08,
            "cooldown_ticks": 3,
            "stress_gain": 1.2,
        },
        "risk_engine": {
            "max_daily_loss_percent": 0.08,  # 8%
            "max_leverage": 8.0,
            "safe_mode_position_multiplier": 0.30,
            "kill_switch_loss_streak": 7,
        },
        "regime_adaptive": {
            "calm_threshold": 0.006,
            "stressed_threshold": 0.025,
            "critical_threshold": 0.050,
            "calm_multiplier": 1.15,
            "stressed_multiplier": 0.70,
            "critical_multiplier": 0.45,
        },
    },
}


def load_config(config_path: Path) -> dict[str, Any]:
    """Load YAML configuration file.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        Dictionary containing configuration data

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
        PermissionError: If config file is not readable
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        raise
    except PermissionError:
        logger.error(f"Permission denied reading: {config_path}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML in {config_path}: {e}")
        raise


def create_backup(file_path: Path) -> Path:
    """Create a backup copy of a file before overwriting.

    Args:
        file_path: Path to the file to backup

    Returns:
        Path to the backup file

    Raises:
        IOError: If backup creation fails
    """
    if not file_path.exists():
        return file_path  # No backup needed if file doesn't exist

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = file_path.with_suffix(f".{timestamp}.bak")

    try:
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return backup_path
    except (IOError, PermissionError) as e:
        logger.error(f"Failed to create backup of {file_path}: {e}")
        raise


def save_config(config: dict[str, Any], config_path: Path, create_backup_file: bool = True) -> None:
    """Save YAML configuration file with optional backup.

    Args:
        config: Configuration dictionary to save
        config_path: Path where to save the configuration
        create_backup_file: Whether to create a backup of existing file

    Raises:
        PermissionError: If unable to write to file
        IOError: If file write fails
    """
    # Ensure parent directory exists and is writable
    # Note: User-provided paths via --output are allowed anywhere
    # Default paths are within safe repo directories (conf/, config/)

    # Create backup if file exists and requested
    if create_backup_file and config_path.exists():
        create_backup(config_path)

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        logger.info(f"Configuration saved to: {config_path}")
    except PermissionError:
        logger.error(f"Permission denied writing to: {config_path}")
        raise
    except IOError as e:
        logger.error(f"Failed to write configuration to {config_path}: {e}")
        raise


def list_profiles() -> None:
    """List all available calibration profiles.

    Prints formatted information about each profile to stdout.
    """
    print("\n=== Available Calibration Profiles ===\n")
    for profile_name, profile_data in CALIBRATION_PROFILES.items():
        print(f"{profile_name.upper()}")
        print(f"  Description: {profile_data['description']}")
        controllers = [k for k in profile_data if k != 'description']
        print(f"  Controllers: {', '.join(controllers)}")
        print()


def validate_nak_config(nak: dict[str, Any], config_path: Path) -> tuple[bool, list[str]]:
    """Validate NAK controller configuration.

    Args:
        nak: NAK configuration dictionary
        config_path: Path to config file (for error messages)

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    # Check for required parameters
    required_params = [
        "EI_low", "EI_high", "EI_crit", "vol_amber", "vol_red",
        "dd_amber", "dd_red", "delta_r_limit", "r_min", "r_max"
    ]
    missing = [p for p in required_params if p not in nak]
    if missing:
        errors = [f"Missing required parameters: {', '.join(missing)}"]
        return False, errors

    # Use centralized validation from calibration_constants
    is_valid, errors = validate_parameter_invariants("nak", nak)

    # Print validation results
    for error in errors:
        print(f"✗ FAIL: {error}")

    if is_valid:
        print("✓ PASS: All NAK parameter invariants satisfied")

    return is_valid, errors


def validate_dopamine_config(config: dict[str, Any], config_path: Path) -> tuple[bool, list[str]]:
    """Validate Dopamine controller configuration.

    Args:
        config: Dopamine configuration dictionary
        config_path: Path to config file (for error messages)

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    # Check for required dopamine parameters
    required_params = ["discount_gamma", "learning_rate_v", "burst_factor", "base_temperature"]
    missing = [p for p in required_params if p not in config]
    if missing:
        errors = [f"Missing required parameters: {', '.join(missing)}"]
        return False, errors

    # Use centralized validation from calibration_constants
    is_valid, errors = validate_parameter_invariants("dopamine", config)

    # Print validation results
    for error in errors:
        print(f"✗ FAIL: {error}")

    if is_valid:
        print("✓ PASS: All Dopamine parameter invariants satisfied")

    return is_valid, errors


def validate_serotonin_config(config: dict[str, Any], config_path: Path) -> tuple[bool, list[str]]:
    """Validate Serotonin controller configuration.

    Args:
        config: Serotonin configuration dictionary
        config_path: Path to config file (for error messages)

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    # Use centralized validation from calibration_constants
    is_valid, errors = validate_parameter_invariants("serotonin", config)

    # Print validation results
    for error in errors:
        print(f"✗ FAIL: {error}")

    if is_valid:
        print("✓ PASS: All Serotonin parameter invariants satisfied")

    return is_valid, errors


def validate_risk_engine_config(config: dict[str, Any], config_path: Path) -> tuple[bool, list[str]]:
    """Validate Risk Engine configuration.

    Args:
        config: Risk Engine configuration dictionary
        config_path: Path to config file (for error messages)

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    # Use centralized validation from calibration_constants
    is_valid, errors = validate_parameter_invariants("risk_engine", config)

    # Print validation results
    for error in errors:
        print(f"✗ FAIL: {error}")

    if is_valid:
        print("✓ PASS: All Risk Engine parameter invariants satisfied")

    return is_valid, errors


def validate_regime_adaptive_config(config: dict[str, Any], config_path: Path) -> tuple[bool, list[str]]:
    """Validate Regime Adaptive Guard configuration.

    Args:
        config: Regime Adaptive configuration dictionary
        config_path: Path to config file (for error messages)

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    # Use centralized validation from calibration_constants
    is_valid, errors = validate_parameter_invariants("regime_adaptive", config)

    # Print validation results
    for error in errors:
        print(f"✗ FAIL: {error}")

    if is_valid:
        print("✓ PASS: All Regime Adaptive parameter invariants satisfied")

    return is_valid, errors


def validate_config(config_path: Path) -> bool:
    """Validate configuration file parameters.

    Args:
        config_path: Path to the configuration file to validate

    Returns:
        True if configuration is valid, False otherwise
    """
    try:
        config = load_config(config_path)
    except Exception as e:
        logger.error(f"Failed to load configuration from {config_path}: {e}")
        return False

    # Detect controller type and validate
    if "nak" in config:
        print(f"\n=== Validating NAK Configuration: {config_path} ===\n")
        is_valid, errors = validate_nak_config(config["nak"], config_path)
    elif "stress_threshold" in config or "serotonin" in config:
        print(f"\n=== Validating Serotonin Configuration: {config_path} ===\n")
        sero_config = config.get("serotonin", config)
        is_valid, errors = validate_serotonin_config(sero_config, config_path)
    elif "discount_gamma" in config or "learning_rate_v" in config:
        print(f"\n=== Validating Dopamine Configuration: {config_path} ===\n")
        is_valid, errors = validate_dopamine_config(config, config_path)
    elif "kill_switch_loss_streak" in config or "max_leverage" in config or "max_daily_loss_percent" in config:
        print(f"\n=== Validating Risk Engine Configuration: {config_path} ===\n")
        is_valid, errors = validate_risk_engine_config(config, config_path)
    elif "calm_threshold" in config and "critical_threshold" in config:
        print(f"\n=== Validating Regime Adaptive Configuration: {config_path} ===\n")
        is_valid, errors = validate_regime_adaptive_config(config, config_path)
    else:
        error_msg = f"Unknown configuration type in {config_path}"
        print(f"✗ FAIL: {error_msg}")
        print("Expected one of: NAK, Dopamine, Serotonin, Risk Engine, Regime Adaptive")
        logger.error(error_msg)
        return False

    # Log final result
    if is_valid:
        print("\n✓ Configuration is valid")
        logger.info(f"Configuration validated successfully: {config_path}")
    else:
        print("\n✗ Configuration has validation errors")
        for error in errors:
            logger.error(f"Validation error in {config_path}: {error}")

    return is_valid


def apply_calibration_profile(
    controller: str,
    profile: str,
    output_path: Path | None = None
) -> None:
    """Apply a calibration profile to a controller configuration.

    Args:
        controller: Controller name (nak, dopamine, serotonin, risk_engine, regime_adaptive)
        profile: Profile name ('conservative', 'balanced', or 'aggressive')
        output_path: Optional custom output path for the configuration

    Raises:
        SystemExit: If profile/controller is invalid or operation fails
    """
    if profile not in CALIBRATION_PROFILES:
        error_msg = f"Unknown profile '{profile}'"
        logger.error(error_msg)
        print(f"Error: {error_msg}")
        print(f"Available profiles: {', '.join(CALIBRATION_PROFILES.keys())}")
        sys.exit(1)

    profile_data = CALIBRATION_PROFILES[profile]

    if controller not in profile_data:
        error_msg = f"Profile '{profile}' does not contain settings for '{controller}'"
        logger.error(error_msg)
        print(f"Error: {error_msg}")
        available = [k for k in profile_data if k != 'description']
        print(f"Available controllers in '{profile}' profile: {', '.join(available)}")
        sys.exit(1)

    print(f"\n=== Applying {profile.upper()} profile to {controller.upper()} controller ===\n")
    print(f"Description: {profile_data['description']}\n")
    logger.info(f"Applying {profile} profile to {controller} controller")

    calibration = profile_data[controller]

    # Determine output path
    if output_path is None:
        if controller == "nak":
            output_path = Path(f"conf/nak/{profile}.yaml")
        elif controller == "dopamine":
            output_path = Path(f"config/profiles/dopamine_{profile}.yaml")
        elif controller == "serotonin":
            output_path = Path(f"configs/serotonin_{profile}.yaml")
        elif controller == "risk_engine":
            output_path = Path(f"configs/risk_engine_{profile}.yaml")
        elif controller == "regime_adaptive":
            output_path = Path(f"configs/regime_adaptive_{profile}.yaml")
        else:
            output_path = Path(f"conf/{controller}_{profile}.yaml")

    # Load existing config or create new one
    try:
        if controller == "nak":
            # Load base NAK config
            base_config_path = Path("nak_controller/conf/nak.yaml")
            if base_config_path.exists():
                config = load_config(base_config_path)
                logger.info(f"Loaded base NAK config from {base_config_path}")
            else:
                config = {"nak": {}}
                logger.info("Creating new NAK config (base not found)")

            # Update with calibration values
            if "nak" not in config:
                config["nak"] = {}
            config["nak"].update(calibration)

        elif controller == "dopamine":
            # Load base dopamine config
            base_config_path = Path("config/dopamine.yaml")
            if base_config_path.exists():
                config = load_config(base_config_path)
                logger.info(f"Loaded base Dopamine config from {base_config_path}")
            else:
                config = {}
                logger.info("Creating new Dopamine config (base not found)")

            # Update with calibration values
            config.update(calibration)

        elif controller == "serotonin":
            # Load base serotonin config
            base_config_path = Path("configs/serotonin.yaml")
            if base_config_path.exists():
                config = load_config(base_config_path)
                logger.info(f"Loaded base Serotonin config from {base_config_path}")
            else:
                config = {}
                logger.info("Creating new Serotonin config (base not found)")

            # Update with calibration values
            config.update(calibration)

        elif controller == "risk_engine":
            # Create risk engine config
            config = calibration.copy()
            logger.info("Creating Risk Engine config")

        elif controller == "regime_adaptive":
            # Create regime adaptive config
            config = calibration.copy()
            logger.info("Creating Regime Adaptive config")

        else:
            error_msg = f"Unsupported controller '{controller}'"
            logger.error(error_msg)
            print(f"Error: {error_msg}")
            sys.exit(1)

        # Ensure output directory exists
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create output directory {output_path.parent}: {e}")
            print(f"Error: Cannot create output directory: {e}")
            sys.exit(1)

        # Save calibrated configuration
        save_config(config, output_path)

        print("Calibrated parameters:")
        for key, value in calibration.items():
            print(f"  {key}: {value}")

        print("\n✓ Calibration profile applied successfully")
        print(f"  Output: {output_path}")
        print("\nTo use this configuration:")
        print(f"  - Review the generated file: {output_path}")
        print(f"  - Validate: python scripts/calibrate_controllers.py --validate {output_path}")
        print("  - Deploy by copying to the appropriate location")

        logger.info(f"Successfully applied {profile} profile to {output_path}")

    except Exception as e:
        logger.error(f"Failed to apply calibration profile: {e}")
        print(f"Error: Failed to apply calibration: {e}")
        sys.exit(1)


def main() -> int:
    """Main entry point for calibration utility.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        description="Calibrate TradePulse controller thresholds and sensitivity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available profiles
  python scripts/calibrate_controllers.py --list-profiles

  # Apply balanced profile to NAK controller
  python scripts/calibrate_controllers.py --controller nak --profile balanced

  # Apply aggressive profile to dopamine controller
  python scripts/calibrate_controllers.py --controller dopamine --profile aggressive

  # Validate existing configuration
  python scripts/calibrate_controllers.py --validate conf/nak/default.yaml

  # Apply with custom output path
  python scripts/calibrate_controllers.py --controller nak --profile conservative --output conf/nak/custom.yaml
        """,
    )

    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List all available calibration profiles",
    )

    parser.add_argument(
        "--controller",
        type=str,
        choices=["nak", "dopamine", "serotonin", "risk_engine", "regime_adaptive"],
        help="Controller to calibrate (required with --profile)",
    )

    parser.add_argument(
        "--profile",
        type=str,
        choices=list(CALIBRATION_PROFILES.keys()),
        help="Calibration profile to apply (conservative, balanced, or aggressive)",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for calibrated configuration (optional)",
    )

    parser.add_argument(
        "--validate",
        type=Path,
        help="Validate an existing configuration file",
    )

    parser.add_argument(
        "--dataset",
        type=Path,
        help="Optional dataset used during calibration for provenance tracking",
    )

    args = parser.parse_args()

    if args.dataset:
        dataset_path = args.dataset.resolve()
        if not dataset_path.exists():
            logger.error("Dataset not found for provenance tracking: %s", dataset_path)
        else:
            contract = contract_by_path(dataset_path)
            if contract:
                record_run_fingerprint(contract, run_type="calibration")
            else:
                logger.warning("No dataset contract registered for %s", dataset_path)

    # Handle list profiles
    if args.list_profiles:
        list_profiles()
        return 0

    # Handle validation
    if args.validate:
        if not args.validate.exists():
            error_msg = f"Configuration file not found: {args.validate}"
            logger.error(error_msg)
            print(f"Error: {error_msg}")
            return 1
        success = validate_config(args.validate)
        return 0 if success else 1

    # Handle calibration
    if args.controller and args.profile:
        apply_calibration_profile(args.controller, args.profile, args.output)
        return 0

    # No valid action specified
    if not any([args.list_profiles, args.validate, (args.controller and args.profile)]):
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
