# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the math-boundaries operating-domain registry gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.ci.check_math_boundaries import REGISTRY_PATH, check_registry, main

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GATE = _REPO_ROOT / "scripts" / "ci" / "check_math_boundaries.py"


def _good_kernel() -> dict[str, Any]:
    return {
        "id": "k1",
        "name": "Kernel One",
        "source": "scripts/ci/check_math_boundaries.py",  # a file that exists
        "invariants": ["INV-OK"],
        "valid": "valid domain",
        "degraded": "degraded domain",
        "invalid": "invalid domain",
        "falsifier": "what would falsify",
    }


KNOWN = {"INV-OK", "INV-ALSO"}


def test_repository_registry_is_consistent() -> None:
    """The shipped docs/math_boundaries.yaml passes its own gate."""
    assert main() == 0


def test_registry_file_present() -> None:
    assert REGISTRY_PATH.exists()


def test_gate_runs_as_documented_path_invocation() -> None:
    """Invoke the gate exactly as its shebang/acceptor documents.

    ``python scripts/ci/check_math_boundaries.py`` from the repo root sets
    ``sys.path[0]`` to ``scripts/ci`` — NOT the repo root. A package import of
    ``scripts.count_invariants`` raises ``ModuleNotFoundError`` under that
    invocation while still passing under pytest, so the in-process ``main()``
    tests above cannot catch the regression. This runs the real command line.
    """
    proc = subprocess.run(
        [sys.executable, str(_GATE)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"documented path invocation must exit 0; got {proc.returncode}\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    assert "Math-boundaries registry passed" in proc.stdout


def test_valid_registry_has_no_errors(tmp_path: Any) -> None:
    reg = {"version": 1, "kernels": [_good_kernel()]}
    assert check_registry(reg, known_invariants=KNOWN, root=REGISTRY_PATH.parents[1]) == []


def test_empty_kernels_fails() -> None:
    errors = check_registry({"kernels": []}, known_invariants=KNOWN, root=REGISTRY_PATH.parents[1])
    assert any("non-empty list" in e for e in errors)


def test_missing_text_field_fails() -> None:
    k = _good_kernel()
    del k["falsifier"]
    errors = check_registry({"kernels": [k]}, known_invariants=KNOWN, root=REGISTRY_PATH.parents[1])
    assert any("falsifier" in e for e in errors)


def test_unknown_invariant_fails() -> None:
    k = _good_kernel()
    k["invariants"] = ["INV-DOES-NOT-EXIST"]
    errors = check_registry({"kernels": [k]}, known_invariants=KNOWN, root=REGISTRY_PATH.parents[1])
    assert any("unknown invariant" in e for e in errors)


def test_missing_source_path_fails() -> None:
    k = _good_kernel()
    k["source"] = "core/does/not/exist.py"
    errors = check_registry({"kernels": [k]}, known_invariants=KNOWN, root=REGISTRY_PATH.parents[1])
    assert any("source path does not exist" in e for e in errors)


def test_duplicate_ids_fail() -> None:
    reg = {"kernels": [_good_kernel(), _good_kernel()]}
    errors = check_registry(reg, known_invariants=KNOWN, root=REGISTRY_PATH.parents[1])
    assert any("duplicate kernel id" in e for e in errors)
