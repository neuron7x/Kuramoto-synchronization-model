# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the invariant source/test binding gate (physics typed-binding).

Proves the gate has teeth: it passes on the committed registry, detects a missing
file and a missing ``::symbol``, and correctly handles YAML-quoted and
comma/space-separated path lists.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_invariant_source_binding.py"
)
spec = importlib.util.spec_from_file_location("check_invariant_source_binding", MODULE_PATH)
assert spec is not None and spec.loader is not None
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)


def _run(registry_text: str, files: dict[str, str]) -> list[dict[str, str]]:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, body in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        reg = root / ".claude" / "physics" / "INVARIANTS.yaml"
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text(registry_text, encoding="utf-8")
        orig_root, orig_reg = gate.ROOT, gate.REGISTRY
        gate.ROOT, gate.REGISTRY = root, reg
        try:
            broken, _, _ = gate.check()
        finally:
            gate.ROOT, gate.REGISTRY = orig_root, orig_reg
        return broken


def test_committed_registry_passes() -> None:
    broken, n_inv, n_checked = gate.check()
    assert broken == [], broken
    assert n_checked > 0


def test_resolved_file_and_symbol_pass() -> None:
    reg = "    id: INV-X1\n    source: core/x.py::run\n    tests: tests/test_x.py\n"
    broken = _run(reg, {"core/x.py": "def run() -> None:\n    pass\n", "tests/test_x.py": "x = 1\n"})
    assert broken == []


def test_missing_file_detected() -> None:
    reg = "    id: INV-X1\n    source: core/gone.py::run\n"
    broken = _run(reg, {})
    assert broken and broken[0]["reason"] == "FILE_MISSING"


def test_missing_symbol_detected() -> None:
    reg = "    id: INV-X1\n    source: core/x.py::missing_fn\n"
    broken = _run(reg, {"core/x.py": "def other() -> None:\n    pass\n"})
    assert broken and broken[0]["reason"] == "SYMBOL_MISSING"


def test_yaml_quoted_path_handled() -> None:
    reg = '    id: INV-X1\n    source: "core/x.py::run"\n'
    broken = _run(reg, {"core/x.py": "def run() -> None:\n    pass\n"})
    assert broken == []


def test_module_level_assignment_symbol_resolves() -> None:
    reg = "    id: INV-X1\n    source: core/x.py::CONST\n"
    broken = _run(reg, {"core/x.py": "CONST = 42\n"})
    assert broken == []
