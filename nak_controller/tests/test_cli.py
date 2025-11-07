from __future__ import annotations

import json
import os
import subprocess
import sys


def test_cli_returns_json_and_zero() -> None:
    env = os.environ.copy()
    cmd = [
        sys.executable,
        "-m",
        "nak_controller.cli.run_validate",
        "--config",
        "nak_controller/conf/nak.yaml",
        "--steps",
        "10",
        "--seeds",
        "1",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert "baseline" in payload and "nak" in payload
