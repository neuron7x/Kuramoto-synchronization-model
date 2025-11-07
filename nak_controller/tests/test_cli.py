"""Smoke tests for the CLI."""
from __future__ import annotations

import json
import subprocess
import sys

from nak_controller.conf import DEFAULT_CONFIG_PATH


def test_cli_returns_json_and_zero() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nak_controller.cli.run_validate",
            "--steps",
            "10",
            "--seeds",
            "1",
            "--config",
            str(DEFAULT_CONFIG_PATH),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert "baseline" in data and "nak" in data
