from __future__ import annotations

import subprocess
import sys


def test_claim_hashes_verify() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/verify_claim_hashes.py"],
        check=False,
    )
    assert proc.returncode == 0
