# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for NaK controller CLI interfaces.

Security note: subprocess usage is acceptable here as we're running
trusted code with validated arguments in a test environment.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_cli_returns_json_and_zero() -> None:
    """Test that the validation CLI produces valid JSON output and exits successfully.

    This test validates:
    - CLI accepts proper arguments
    - Returns valid JSON structure
    - Exits with code 0 on success
    - Output contains expected keys and valid numeric data
    """
    env = os.environ.copy()
    env.setdefault("NAK_SEED", "1337")
    env.setdefault("PYTHONHASHSEED", "0")

    # Validate config file exists before running
    config_path = Path("nak_controller/conf/nak.yaml")
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    # Build command with validated arguments
    # Note: All arguments are hardcoded constants, not user input
    cmd = [
        sys.executable,  # Trusted Python interpreter
        "-m",
        "nak_controller.cli.run_validate",  # Trusted module
        "--config",
        str(config_path),  # Validated path
        "--steps",
        "50",  # Constant numeric argument
        "--seeds",
        "1",  # Constant numeric argument
        "--seed",
        "1337",  # Constant numeric argument
    ]

    # Run with timeout to prevent hanging
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env, timeout=30)

    assert proc.returncode == 0, f"CLI failed with stderr: {proc.stderr}"

    # Validate JSON output
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(f"Invalid JSON output: {error}\nOutput: {proc.stdout}") from error

    # Validate expected structure
    assert set(payload) == {
        "baseline",
        "nak",
    }, f"Unexpected keys in output: {set(payload)}"
    assert "avg_risk_per_trade" in payload["baseline"], "Missing avg_risk_per_trade in baseline"
    assert payload["baseline"]["avg_risk_per_trade"] > 0.0, "avg_risk_per_trade must be positive"
