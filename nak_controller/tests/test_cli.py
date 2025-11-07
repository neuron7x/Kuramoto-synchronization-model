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
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    payload = json.loads(proc.stdout)
    if "baseline" not in payload or "nak" not in payload:
        raise AssertionError("expected baseline and nak results")
