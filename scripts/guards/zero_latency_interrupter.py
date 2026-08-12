from __future__ import annotations

import subprocess
import sys


def main() -> int:
    result = subprocess.run(
        [sys.executable, "scripts/check_epistemic_drift.py"],
        check=False,
    )
    if result.returncode != 0:
        print("ZERO-LATENCY INTERRUPTER: epistemic noise detected (Δ > 0). " "Execution blocked.")
        return 1
    print("ZERO-LATENCY INTERRUPTER: clean state, execution allowed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
