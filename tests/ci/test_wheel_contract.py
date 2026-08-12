# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the wheel-contract gate parser and failure modes (WP-01).

The full gate builds a wheel (heavy, covered by CI); here we test the pure units:
the AST import extractor, the latent-broken-import detection rule (a packaged
module importing an unpackaged first-party namespace, e.g. tools -> excluded
cli), and the baseline ratchet round-trip.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_wheel_contract.py"
)
spec = importlib.util.spec_from_file_location("check_wheel_contract", MODULE_PATH)
assert spec is not None and spec.loader is not None
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)


class ImportExtractorTest(unittest.TestCase):
    def test_extracts_import_and_from(self) -> None:
        src = "import tools.foo\nfrom cli import bar\nimport os\nfrom . import rel\n"
        tops = gate._imported_top_levels(src)
        self.assertEqual(tops, {"tools", "cli", "os"})

    def test_relative_import_ignored(self) -> None:
        self.assertEqual(gate._imported_top_levels("from . import x\nfrom .y import z\n"), set())

    def test_syntax_error_is_safe(self) -> None:
        self.assertEqual(gate._imported_top_levels("def ("), set())


class LatentBrokenImportRuleTest(unittest.TestCase):
    def test_tools_importing_excluded_cli_is_a_violation(self) -> None:
        """The canonical synthetic fixture: packaged tools imports unpackaged cli."""
        installed = {"tools", "geosync"}
        first_party = {"tools", "cli", "geosync"}
        stdlib = gate._stdlib_names()
        source = "from cli.geosync_cli import cli\nimport json\n"
        violations = [
            imp
            for imp in gate._imported_top_levels(source)
            if imp not in stdlib and imp not in installed and imp in first_party
        ]
        self.assertEqual(violations, ["cli"])

    def test_packaged_import_is_not_a_violation(self) -> None:
        installed = {"tools", "geosync"}
        first_party = {"tools", "cli", "geosync"}
        stdlib = gate._stdlib_names()
        source = "import geosync.mfn\nimport numpy\n"  # geosync packaged, numpy third-party
        violations = [
            imp
            for imp in gate._imported_top_levels(source)
            if imp not in stdlib and imp not in installed and imp in first_party
        ]
        self.assertEqual(violations, [])


class BaselineRoundTripTest(unittest.TestCase):
    def test_write_then_load(self) -> None:
        with TemporaryDirectory() as tmp:
            orig = gate.BASELINE_PATH
            gate.BASELINE_PATH = Path(tmp) / "bwheel_baseline.json"
            try:
                failures = [
                    {"module": "tools/x.py", "imports_unpackaged": "cli"},
                    {"module": "scripts/y.py", "imports_unpackaged": "research"},
                ]
                gate._write_baseline({"tools", "core"}, failures)
                pkgs, debt = gate._load_baseline()
                self.assertEqual(pkgs, {"tools", "core"})
                self.assertEqual(debt, {"tools/x.py::cli", "scripts/y.py::research"})
                payload = json.loads(gate.BASELINE_PATH.read_text())
                self.assertIn("tools", payload["allowed_legacy_packages"])
                self.assertEqual(payload["version"], 1)
            finally:
                gate.BASELINE_PATH = orig

    def test_missing_baseline_is_empty(self) -> None:
        orig = gate.BASELINE_PATH
        gate.BASELINE_PATH = Path("/nonexistent/bwheel_baseline.json")
        try:
            self.assertEqual(gate._load_baseline(), (set(), set()))
        finally:
            gate.BASELINE_PATH = orig


if __name__ == "__main__":
    unittest.main()
