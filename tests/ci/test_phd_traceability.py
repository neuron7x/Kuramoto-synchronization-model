# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the PhD research-claim traceability gate (Phase-2).

Proves the gate has teeth: it passes on the committed dissertation, fails on an
unbound chapter (no artifact reference) and on a forbidden positive over-claim,
and correctly EXEMPTS honest disclaimers / quoted references.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_phd_traceability.py"
)
spec = importlib.util.spec_from_file_location("check_phd_traceability", MODULE_PATH)
assert spec is not None and spec.loader is not None
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)


def _run(files: dict[str, str]) -> tuple[int, dict[str, object]]:
    with TemporaryDirectory() as tmp:
        phd = Path(tmp) / "docs" / "phd"
        phd.mkdir(parents=True)
        for name, body in files.items():
            (phd / name).write_text(body, encoding="utf-8")
        out = Path(tmp) / "out.json"
        orig_dir, orig_root = gate.PHD_DIR, gate.ROOT
        gate.PHD_DIR = phd
        gate.ROOT = Path(tmp)
        try:
            rc = gate.main(["--json", str(out)])
        finally:
            gate.PHD_DIR, gate.ROOT = orig_dir, orig_root
        return rc, json.loads(out.read_text())


def test_committed_dissertation_passes() -> None:
    assert gate.main(["--json", "/tmp/phd_trace_real.json"]) == 0


def test_bound_chapter_passes() -> None:
    rc, rep = _run({"06_x.md": "Method uses scripts/ci/check_wheel_contract.py and PR #1302."})
    assert rc == 0
    assert rep["unbound_claims"] == []


def test_unbound_chapter_fails() -> None:
    rc, rep = _run({"06_x.md": "A grand methodological assertion with no reference at all."})
    assert rc == 1
    assert "docs/phd/06_x.md" in rep["unbound_claims"]


def test_forbidden_positive_overclaim_fails() -> None:
    rc, rep = _run({"06_x.md": "The strategy is profitable. See scripts/ci/x.py."})
    assert rc == 1
    assert any(f["file"] == "docs/phd/06_x.md" for f in rep["forbidden_terms"])


def test_disclaimer_is_exempt() -> None:
    rc, rep = _run(
        {"06_x.md": "This makes no profitable or trading-edge claim. See scripts/ci/x.py."}
    )
    assert rc == 0
    assert rep["forbidden_terms"] == []


def test_quoted_reference_is_exempt() -> None:
    rc, rep = _run({"06_x.md": 'The forbidden term `profitable` is listed. See gate-name-gate.'})
    assert rc == 0


def test_readme_pointer_is_bound() -> None:
    rc, rep = _run({"README.md": "Index of chapters, plain prose pointer."})
    assert rc == 0
    assert "docs/phd/README.md" in rep["claims_with_artifacts"]
