# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the package-boundary ratchet gate.

The ratchet measures the non-geosync top-level packages in the *built wheel*
(git archive HEAD) and enforces monotone shrink: a NEW leak fails; a re-homed
package leaves a stale ledger that also fails until tightened with --write. The
pure comparison is tested directly; main() is tested with the (heavy) wheel
build stubbed; one slow test exercises the real build against the committed
baseline.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_package_boundary.py"
)
spec = importlib.util.spec_from_file_location("check_package_boundary", MODULE_PATH)
assert spec is not None and spec.loader is not None
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)


class EvaluatePureTest(unittest.TestCase):
    def test_equal_sets_pass(self) -> None:
        failed, new, fixed = gate.evaluate({"core", "tools"}, {"core", "tools"})
        self.assertFalse(failed)
        self.assertEqual((new, fixed), ([], []))

    def test_new_leak_fails(self) -> None:
        failed, new, fixed = gate.evaluate({"core", "tools", "evil"}, {"core", "tools"})
        self.assertTrue(failed)
        self.assertEqual(new, ["evil"])

    def test_paydown_is_stale_until_written(self) -> None:
        failed, new, fixed = gate.evaluate({"core"}, {"core", "tools"})
        self.assertTrue(failed)
        self.assertEqual(fixed, ["tools"])


class MainWithStubbedBuildTest(unittest.TestCase):
    def _run(self, current: set[str], baseline: list[str]) -> int:
        with TemporaryDirectory() as tmp:
            base_path = Path(tmp) / "baseline.json"
            base_path.write_text(
                json.dumps({"version": 2, "non_geosync_packages": baseline})
            )
            orig_leak, orig_base = gate._shipped_leak, gate.BASELINE_PATH
            setattr(gate, "_shipped_leak", lambda: set(current))
            gate.BASELINE_PATH = base_path
            try:
                return gate.main([])
            finally:
                setattr(gate, "_shipped_leak", orig_leak)
                gate.BASELINE_PATH = orig_base

    def test_leak_equal_to_baseline_passes(self) -> None:
        self.assertEqual(self._run({"core", "tools"}, ["core", "tools"]), 0)

    def test_new_leak_fails_closed(self) -> None:
        self.assertEqual(self._run({"core", "tools", "evil"}, ["core", "tools"]), 1)

    def test_paydown_leaves_stale_ledger_failing(self) -> None:
        self.assertEqual(self._run({"core"}, ["core", "tools"]), 1)

    def test_geosync_never_counts(self) -> None:
        # _shipped_leak already filters geosync*; an empty leak set is GREEN.
        self.assertEqual(self._run(set(), []), 0)


class RealBuildTest(unittest.TestCase):
    def test_committed_baseline_matches_real_wheel(self) -> None:
        """Slow: build the real wheel from HEAD; it must match the frozen baseline."""
        try:
            cur = gate._shipped_leak()
        except gate.WheelBuildError as exc:  # pragma: no cover - env-dependent
            self.skipTest(f"wheel build unavailable: {exc}")
        base = gate._load_baseline()
        failed, new, fixed = gate.evaluate(cur, base)
        self.assertFalse(failed, f"new={new} fixed={fixed}")


if __name__ == "__main__":
    unittest.main()
