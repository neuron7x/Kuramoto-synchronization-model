# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GOV-002 — tests for the RACI closure gate (scripts/ci/check_raci.py).

Positive: the committed governance/REMEDIATION_RACI.yaml passes (exit 0).
Negative: a RACI missing a workstream fails (non-zero exit).
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "ci" / "check_raci.py"
RACI = ROOT / "governance" / "REMEDIATION_RACI.yaml"


def _run(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK), str(target)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )


class RaciGateTest(unittest.TestCase):
    def test_committed_raci_passes(self) -> None:
        result = _run(RACI)
        self.assertEqual(
            result.returncode,
            0,
            msg=f"check_raci.py should exit 0 on the real RACI.\n"
            f"stdout={result.stdout}\nstderr={result.stderr}",
        )

    def test_missing_workstream_fails(self) -> None:
        data = yaml.safe_load(RACI.read_text(encoding="utf-8"))
        # Drop one workstream from the matrix -> must fail closed.
        removed = data["raci"].pop("OPS")
        self.assertIsNotNone(removed)
        tmp = ROOT / "tests" / "ci" / "_tmp_raci_missing_ws.yaml"
        tmp.write_text(yaml.safe_dump(data), encoding="utf-8")
        try:
            result = _run(tmp)
        finally:
            tmp.unlink(missing_ok=True)
        self.assertNotEqual(
            result.returncode,
            0,
            msg="check_raci.py must reject a RACI missing a workstream.",
        )
        self.assertIn("OPS", result.stderr)

    def test_missing_coi_rule_fails(self) -> None:
        data = yaml.safe_load(RACI.read_text(encoding="utf-8"))
        data.pop("conflict_of_interest", None)
        data.pop("two_signature_rule", None)
        tmp = ROOT / "tests" / "ci" / "_tmp_raci_no_coi.yaml"
        tmp.write_text(yaml.safe_dump(data), encoding="utf-8")
        try:
            result = _run(tmp)
        finally:
            tmp.unlink(missing_ok=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
