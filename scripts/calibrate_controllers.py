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
import sys
from pathlib import Path
from typing import Any, Dict

import yaml

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
    """Load YAML configuration file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config: Dict[str, Any], config_path: Path) -> None:
    """Save YAML configuration file."""
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def list_profiles() -> None:
    """List all available calibration profiles."""
    print("\n=== Available Calibration Profiles ===\n")
    for profile_name, profile_data in CALIBRATION_PROFILES.items():
        print(f"{profile_name.upper()}")
        print(f"  Description: {profile_data['description']}")
        print(f"  Controllers: {', '.join([k for k in profile_data if k != 'description'])}")
        print()


def validate_config(config_path: Path) -> bool:
    """Validate configuration file parameters."""
    try:
        config = load_config(config_path)
        
        # Check if it's a NAK config
        if "nak" in config:
            nak = config["nak"]
            print(f"\n=== Validating NAK Configuration: {config_path} ===\n")
            
            # Check for required parameters
            required_params = ["EI_low", "EI_high", "EI_crit", "vol_amber", "vol_red", 
                              "dd_amber", "dd_red", "delta_r_limit", "r_min", "r_max"]
            missing = [p for p in required_params if p not in nak]
            if missing:
                print(f"✗ FAIL: Missing required parameters: {', '.join(missing)}")
                return False
            
            # Validate critical parameters
            checks = [
                (nak["EI_low"] < nak["EI_high"], 
                 "EI_low must be less than EI_high"),
                (nak["EI_crit"] >= 0, 
                 "EI_crit must be non-negative"),
                (nak["EI_crit"] <= nak["EI_low"],
                 "EI_crit must be less than or equal to EI_low"),
                (nak["vol_amber"] <= nak["vol_red"], 
                 "vol_amber must be less than or equal to vol_red"),
                (nak["dd_amber"] <= nak["dd_red"], 
                 "dd_amber must be less than or equal to dd_red"),
                (0 < nak["delta_r_limit"] <= 1.0,
                 "delta_r_limit must be in (0, 1]"),
                (nak["r_min"] < nak["r_max"],
                 "r_min must be less than r_max"),
            ]
            
            all_passed = True
            for passed, message in checks:
                status = "✓ PASS" if passed else "✗ FAIL"
                print(f"{status}: {message}")
                if not passed:
                    all_passed = False
            
            if all_passed:
                print("\n✓ Configuration is valid")
                return True
            else:
                print("\n✗ Configuration has validation errors")
                return False
        
        # Check if it's a dopamine config
        elif "discount_gamma" in config or "learning_rate_v" in config:
            print(f"\n=== Validating Dopamine Configuration: {config_path} ===\n")
            
            # Check for required dopamine parameters
            required_params = ["discount_gamma", "learning_rate_v", "burst_factor", "base_temperature"]
            missing = [p for p in required_params if p not in config]
            if missing:
                print(f"✗ FAIL: Missing required parameters: {', '.join(missing)}")
                return False
            
            checks = [
                (0 < config["discount_gamma"] < 1.0,
                 "discount_gamma must be in (0, 1)"),
                (config["learning_rate_v"] > 0,
                 "learning_rate_v must be positive"),
                (config["burst_factor"] >= 1.0,
                 "burst_factor must be >= 1.0"),
                (config["base_temperature"] > 0,
                 "base_temperature must be positive"),
            ]
            
            all_passed = True
            for passed, message in checks:
                status = "✓ PASS" if passed else "✗ FAIL"
                print(f"{status}: {message}")
                if not passed:
                    all_passed = False
            
            if all_passed:
                print("\n✓ Configuration is valid")
                return True
            else:
                print("\n✗ Configuration has validation errors")
                return False
        
        else:
            print(f"Unknown configuration type in {config_path}")
            return False
            
    except Exception as e:
        print(f"Error validating {config_path}: {e}")
        return False


def apply_calibration_profile(
    controller: str, 
    profile: str, 
    output_path: Path | None = None
) -> None:
    """Apply a calibration profile to a controller configuration."""
    if profile not in CALIBRATION_PROFILES:
        print(f"Error: Unknown profile '{profile}'")
        print(f"Available profiles: {', '.join(CALIBRATION_PROFILES.keys())}")
        sys.exit(1)
    
    profile_data = CALIBRATION_PROFILES[profile]
    
    if controller not in profile_data:
        print(f"Error: Profile '{profile}' does not contain settings for '{controller}'")
        sys.exit(1)
    
    print(f"\n=== Applying {profile.upper()} profile to {controller.upper()} controller ===\n")
    print(f"Description: {profile_data['description']}\n")
    
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
    if controller == "nak":
        # Load base NAK config
        base_config_path = Path("nak_controller/conf/nak.yaml")
        if base_config_path.exists():
            config = load_config(base_config_path)
        else:
            config = {"nak": {}}
        
        # Update with calibration values
        if "nak" not in config:
            config["nak"] = {}
        config["nak"].update(calibration)
    
    elif controller == "dopamine":
        # Load base dopamine config
        base_config_path = Path("config/dopamine.yaml")
        if base_config_path.exists():
            config = load_config(base_config_path)
        else:
            config = {}
        
        # Update with calibration values
        config.update(calibration)
    
    else:
        print(f"Error: Unsupported controller '{controller}'")
        sys.exit(1)
    
    # Save calibrated configuration
    output_path.parent.mkdir(parents=True, exist_ok=True)
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


def main() -> None:
    """Main entry point for calibration utility."""
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
        help="Controller to calibrate",
    )
    
    parser.add_argument(
        "--profile",
        type=str,
        choices=list(CALIBRATION_PROFILES.keys()),
        help="Calibration profile to apply",
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
        return
    
    # Handle validation
    if args.validate:
        if not args.validate.exists():
            print(f"Error: Configuration file not found: {args.validate}")
            sys.exit(1)
        success = validate_config(args.validate)
        sys.exit(0 if success else 1)
    
    # Handle calibration
    if args.controller and args.profile:
        apply_calibration_profile(args.controller, args.profile, args.output)
        return
    
    # No valid action specified
    if not any([args.list_profiles, args.validate, (args.controller and args.profile)]):
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
