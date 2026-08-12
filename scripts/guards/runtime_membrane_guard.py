#!/usr/bin/env python3
"""Runtime membrane guard: geosync runtime must not have coherence_bridge on import path."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEOSYNC_PATH = str(ROOT / "geosync")

CODE = r"""
import importlib
import sys

if '' in sys.path:
    sys.path.remove('')

try:
    importlib.import_module('coherence_bridge')
except ModuleNotFoundError:
    print('Runtime membrane passed: coherence_bridge not importable in isolated geosync path.')
    raise SystemExit(0)

print('Runtime membrane FAILED: coherence_bridge importable under isolated geosync path.')
raise SystemExit(1)
"""


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = GEOSYNC_PATH

    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [sys.executable, "-c", CODE],
            cwd=tmp,
            env=env,
            text=True,
            capture_output=True,
        )
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip())
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
