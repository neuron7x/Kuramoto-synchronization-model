from __future__ import annotations

import json
import os
import subprocess
import sys


def test_cli_returns_json_and_zero() -> None:
    env = os.environ.copy()
    env.setdefault("NAK_SEED", "1337")
    env.setdefault("PYTHONHASHSEED", "0")
    cmd = [
        sys.executable,
        "-m",
        "nak_controller.cli.run_validate",
        "--config",
        "nak_controller/conf/nak.yaml",
        "--steps",
        "50",
        "--seeds",
        "1",
        "--seed",
        "1337",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert set(payload) == {"baseline", "nak"}
    assert payload["baseline"]["avg_risk_per_trade"] > 0.0
