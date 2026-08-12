#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Generate Thermodynamics Token

Generates secure tokens for manual override and dual approval operations.
Used by security team for TACL manual interventions.
"""

import argparse
import secrets
import sys
from datetime import datetime, timedelta


def generate_token(length: int = 32) -> str:
    """Generate a cryptographically secure token."""
    return secrets.token_urlsafe(length)


def main():
    parser = argparse.ArgumentParser(
        description="Generate secure token for thermodynamic manual override"
    )

    parser.add_argument(
        "--duration",
        type=str,
        default="1h",
        help="Token validity duration (e.g., 1h, 24h, 7d)",
    )

    parser.add_argument(
        "--length", type=int, default=32, help="Token length in bytes (default: 32)"
    )

    parser.add_argument(
        "--type",
        choices=["override", "dual_approval"],
        default="override",
        help="Token type",
    )

    args = parser.parse_args()

    # Parse duration
    duration_str = args.duration.lower()
    if duration_str.endswith("h"):
        hours = int(duration_str[:-1])
    elif duration_str.endswith("d"):
        hours = int(duration_str[:-1]) * 24
    elif duration_str.endswith("m"):
        hours = int(duration_str[:-1]) / 60
    else:
        print(
            f"Error: Invalid duration format '{args.duration}'. Use format like '1h', '24h', or '7d'"
        )
        return 1

    expiration = datetime.now() + timedelta(hours=hours)

    # Generate token
    token = generate_token(args.length)

    # Display token information
    print("=" * 70)
    print("THERMODYNAMIC TOKEN")
    print("=" * 70)
    print(f"\nToken Type:    {args.type}")
    print(f"Generated At:  {datetime.now().isoformat()}")
    print(f"Expires At:    {expiration.isoformat()}")
    print(f"Valid For:     {args.duration}")
    print("\nToken (copy to environment variable):")
    print("-" * 70)
    print(token)
    print("-" * 70)

    # Usage instructions
    print("\nUsage:")
    if args.type == "override":
        print(f"  export THERMO_OVERRIDE_TOKEN='{token}'")
        print("\n  Then use manual override endpoint:")
        print("  curl -X POST http://localhost:8080/thermo/override \\")
        print("    -H 'Content-Type: application/json' \\")
        print(f'    -d \'{{"token": "{token}", "reason": "Your reason here"}}\'')
    else:
        print(f"  export THERMO_DUAL_TOKEN='{token}'")
        print("\n  The controller will use this token for dual approval checks.")

    print("\n" + "=" * 70)
    print("⚠️  SECURITY NOTICE:")
    print("  - Store this token securely")
    print("  - Do not commit to version control")
    print("  - Revoke after use or expiration")
    print("  - Log all token usage for audit trail")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
