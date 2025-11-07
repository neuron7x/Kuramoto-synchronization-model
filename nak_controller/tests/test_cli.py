"""Smoke tests for the CLI."""
from __future__ import annotations

import json
import subprocess
import sys


def test_cli_returns_json_and_zero() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nak_controller.cli.run_validate",
            "--config",
            "nak_controller/conf/nak.yaml",
            "--steps",
            "10",
            "--seeds",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert "baseline" in data and "nak" in data
