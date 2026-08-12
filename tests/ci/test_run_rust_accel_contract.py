from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "ci"
    / "run_rust_accel_contract.py"
)
spec = importlib.util.spec_from_file_location("run_rust_accel_contract", MODULE_PATH)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


class RunRustAccelContractSmokeTests(unittest.TestCase):
    def test_dry_run_emits_json_plan(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = runner.main(["--dry-run", "--format", "json"])

        self.assertEqual(exit_code, 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["status"], "DRY_RUN")
        self.assertTrue(report["dry_run"])
        self.assertGreaterEqual(len(report["criteria"]), 1)
        self.assertIn("tool_versions", report)


if __name__ == "__main__":
    unittest.main()
