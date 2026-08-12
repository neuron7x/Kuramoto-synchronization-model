from __future__ import annotations

import subprocess
import sys


def test_production_readiness_script_passes() -> None:
    proc = subprocess.run([sys.executable, "scripts/production_readiness_riee.py"], check=False)
    assert proc.returncode == 0
