# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the executable-falsifier ledger gate.

The gate proves that every declared null/falsifier resolves to real code (an
impl_file defining its symbol) and an executable witness (a test_file). It must
pass on the committed ledger and fail closed the moment a falsifier rots into
prose (missing file, renamed symbol, or absent witness).
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_falsifier_ledger.py"
)
spec = importlib.util.spec_from_file_location("check_falsifier_ledger", MODULE_PATH)
assert spec is not None and spec.loader is not None
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)


def _good_entry() -> dict[str, object]:
    return {
        "id": "permutation_null",
        "kind": "null_model",
        "impl_file": "research/askar/ricci_spread.py",
        "symbol": "permutation_test",
        "test_file": "tests/askar/test_ricci_spread.py",
        "description": "real null",
    }


class FalsifierLedgerGateTest(unittest.TestCase):
    def test_committed_ledger_resolves_green(self) -> None:
        """The real ledger in the tree must pass (every falsifier executable)."""
        self.assertEqual(gate.main([]), 0)

    def test_good_entry_resolves(self) -> None:
        status, problems = gate._check_entry(_good_entry())
        self.assertEqual(status, "RESOLVED", problems)
        self.assertEqual(problems, [])

    def test_missing_impl_file_is_broken(self) -> None:
        entry = _good_entry()
        entry["impl_file"] = "research/askar/does_not_exist.py"
        status, problems = gate._check_entry(entry)
        self.assertEqual(status, "BROKEN")
        self.assertTrue(any("impl_file missing" in p for p in problems))

    def test_renamed_symbol_is_broken(self) -> None:
        entry = _good_entry()
        entry["symbol"] = "this_function_was_renamed_away"
        status, problems = gate._check_entry(entry)
        self.assertEqual(status, "BROKEN")
        self.assertTrue(any("not defined" in p for p in problems))

    def test_missing_witness_is_broken(self) -> None:
        entry = _good_entry()
        entry["test_file"] = "tests/askar/no_such_witness.py"
        status, problems = gate._check_entry(entry)
        self.assertEqual(status, "BROKEN")
        self.assertTrue(any("witness) missing" in p for p in problems))

    def test_missing_required_field_is_malformed(self) -> None:
        entry = _good_entry()
        del entry["symbol"]
        status, problems = gate._check_entry(entry)
        self.assertEqual(status, "MALFORMED")
        self.assertTrue(any("missing field" in p for p in problems))

    def test_unknown_kind_is_broken(self) -> None:
        entry = _good_entry()
        entry["kind"] = "decorative"
        status, problems = gate._check_entry(entry)
        self.assertEqual(status, "BROKEN")
        self.assertTrue(any("kind" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
