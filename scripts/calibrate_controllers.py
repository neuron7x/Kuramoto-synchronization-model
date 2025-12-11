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
from typing import Any, Dict, List, Tuple

import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Parameter range constants for validation (single source of truth)
class ParameterRanges:
    """Parameter bounds for validation."""
    # NAK Controller ranges
    EI_RANGE = (0.0, 1.0)
    VOL_RANGE = (0.0, 2.0)
    DD_RANGE = (0.0, 1.0)
    DELTA_R_RANGE = (0.0, 1.0)
    RISK_RANGE = (0.0, 1.0)
    
    # Dopamine Controller ranges
    DISCOUNT_GAMMA_RANGE = (0.0, 1.0)
    LEARNING_RATE_MIN = 0.0
    BURST_FACTOR_MIN = 1.0
    TEMPERATURE_MIN = 0.0

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
    },
}


def load_config(config_path: Path) -> Dict[str, Any]:
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


def save_config(config: Dict[str, Any], config_path: Path, create_backup_file: bool = True) -> None:
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
    # Default paths are within safe repo directories (conf/, config/, artifacts/)
    
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


def validate_nak_config(nak: Dict[str, Any], config_path: Path) -> Tuple[bool, List[str]]:
    """Validate NAK controller configuration.
    
    Args:
        nak: NAK configuration dictionary
        config_path: Path to config file (for error messages)
        
    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []
    
    # Check for required parameters
    required_params = ["EI_low", "EI_high", "EI_crit", "vol_amber", "vol_red", 
                      "dd_amber", "dd_red", "delta_r_limit", "r_min", "r_max"]
    missing = [p for p in required_params if p not in nak]
    if missing:
        errors.append(f"Missing required parameters: {', '.join(missing)}")
        return False, errors
    
    # Validate critical parameters using constants
    checks: List[Tuple[bool, str, str]] = [
        (nak["EI_low"] < nak["EI_high"],
         "EI_low must be less than EI_high",
         f"EI_low={nak['EI_low']}, EI_high={nak['EI_high']}"),
        (ParameterRanges.EI_RANGE[0] <= nak["EI_crit"] <= ParameterRanges.EI_RANGE[1],
         f"EI_crit must be in range {ParameterRanges.EI_RANGE}",
         f"EI_crit={nak['EI_crit']}"),
        (nak["EI_crit"] <= nak["EI_low"],
         "EI_crit must be less than or equal to EI_low",
         f"EI_crit={nak['EI_crit']}, EI_low={nak['EI_low']}"),
        (nak["vol_amber"] <= nak["vol_red"],
         "vol_amber must be less than or equal to vol_red",
         f"vol_amber={nak['vol_amber']}, vol_red={nak['vol_red']}"),
        (nak["dd_amber"] <= nak["dd_red"],
         "dd_amber must be less than or equal to dd_red",
         f"dd_amber={nak['dd_amber']}, dd_red={nak['dd_red']}"),
        (0 < nak["delta_r_limit"] <= 1.0,
         "delta_r_limit must be in (0, 1]",
         f"delta_r_limit={nak['delta_r_limit']}"),
        (nak["r_min"] < nak["r_max"],
         "r_min must be less than r_max",
         f"r_min={nak['r_min']}, r_max={nak['r_max']}"),
    ]
    
    all_passed = True
    for passed, message, details in checks:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {message}")
        if not passed:
            all_passed = False
            errors.append(f"{message} ({details})")
    
    return all_passed, errors


def validate_dopamine_config(config: Dict[str, Any], config_path: Path) -> Tuple[bool, List[str]]:
    """Validate Dopamine controller configuration.
    
    Args:
        config: Dopamine configuration dictionary
        config_path: Path to config file (for error messages)
        
    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []
    
    # Check for required dopamine parameters
    required_params = ["discount_gamma", "learning_rate_v", "burst_factor", "base_temperature"]
    missing = [p for p in required_params if p not in config]
    if missing:
        errors.append(f"Missing required parameters: {', '.join(missing)}")
        return False, errors
    
    checks: List[Tuple[bool, str, str]] = [
        (ParameterRanges.DISCOUNT_GAMMA_RANGE[0] < config["discount_gamma"] < ParameterRanges.DISCOUNT_GAMMA_RANGE[1],
         f"discount_gamma must be in {ParameterRanges.DISCOUNT_GAMMA_RANGE}",
         f"discount_gamma={config['discount_gamma']}"),
        (config["learning_rate_v"] > ParameterRanges.LEARNING_RATE_MIN,
         f"learning_rate_v must be > {ParameterRanges.LEARNING_RATE_MIN}",
         f"learning_rate_v={config['learning_rate_v']}"),
        (config["burst_factor"] >= ParameterRanges.BURST_FACTOR_MIN,
         f"burst_factor must be >= {ParameterRanges.BURST_FACTOR_MIN}",
         f"burst_factor={config['burst_factor']}"),
        (config["base_temperature"] > ParameterRanges.TEMPERATURE_MIN,
         f"base_temperature must be > {ParameterRanges.TEMPERATURE_MIN}",
         f"base_temperature={config['base_temperature']}"),
    ]
    
    all_passed = True
    for passed, message, details in checks:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {message}")
        if not passed:
            all_passed = False
            errors.append(f"{message} ({details})")
    
    return all_passed, errors


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
    
    # Check if it's a NAK config
    if "nak" in config:
        print(f"\n=== Validating NAK Configuration: {config_path} ===\n")
        is_valid, errors = validate_nak_config(config["nak"], config_path)
        
        if is_valid:
            print("\n✓ Configuration is valid")
            logger.info(f"NAK configuration validated successfully: {config_path}")
        else:
            print("\n✗ Configuration has validation errors")
            for error in errors:
                logger.error(f"Validation error in {config_path}: {error}")
        return is_valid
    
    # Check if it's a dopamine config
    elif "discount_gamma" in config or "learning_rate_v" in config:
        print(f"\n=== Validating Dopamine Configuration: {config_path} ===\n")
        is_valid, errors = validate_dopamine_config(config, config_path)
        
        if is_valid:
            print("\n✓ Configuration is valid")
            logger.info(f"Dopamine configuration validated successfully: {config_path}")
        else:
            print("\n✗ Configuration has validation errors")
            for error in errors:
                logger.error(f"Validation error in {config_path}: {error}")
        return is_valid
    
    else:
        error_msg = f"Unknown configuration type in {config_path} (expected 'nak' key or dopamine parameters)"
        print(f"✗ FAIL: {error_msg}")
        logger.error(error_msg)
        return False


def apply_calibration_profile(
    controller: str, 
    profile: str, 
    output_path: Path | None = None
) -> None:
    """Apply a calibration profile to a controller configuration.
    
    Args:
        controller: Controller name ('nak' or 'dopamine')
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
            output_path = Path(f"config/profiles/{profile}.yaml")
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
        
        print(f"Calibrated parameters:")
        for key, value in calibration.items():
            print(f"  {key}: {value}")
        
        print(f"\n✓ Calibration profile applied successfully")
        print(f"  Output: {output_path}")
        print(f"\nTo use this configuration:")
        print(f"  - Review the generated file: {output_path}")
        print(f"  - Validate: python scripts/calibrate_controllers.py --validate {output_path}")
        print(f"  - Deploy by copying to the appropriate location")
        
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
        choices=["nak", "dopamine"],
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
    
    args = parser.parse_args()
    
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
