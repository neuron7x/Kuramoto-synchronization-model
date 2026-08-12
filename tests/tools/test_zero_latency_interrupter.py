from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_zero_latency_interrupter_runs() -> None:
    script = Path("scripts") / "guards" / "zero_latency_interrupter.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        check=False,
    )
    assert proc.returncode == 0
