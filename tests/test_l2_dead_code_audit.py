"""Dead-code audit for the L2 research surface.

Uses `ruff --select F401,F841,F811` to enforce no unused imports, no
unused local variables, no duplicate function definitions across the
L2 research modules, scripts, and tests.

If ruff is not installed, the test skips (so CI-only tooling is fine).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_L2_PATHS = [
    "research/microstructure/",
    "tests/test_l2_*.py",
    "tests/l2_artifacts.py",
]


def _ruff_available() -> bool:
    return shutil.which("ruff") is not None


@pytest.mark.skipif(not _ruff_available(), reason="ruff not installed")
def test_no_unused_imports_or_variables_in_l2_surface() -> None:
    """ruff --select F401,F841,F811 must be silent across L2 paths.

    F401 — unused import
    F841 — unused local variable
    F811 — redefinition of unused name
    """
    cmd = [
        "ruff",
        "check",
        "--select",
        "F401,F841,F811",
        "--no-cache",
        *_L2_PATHS,
    ]
    # Also include every run_l2_*.py + render_l2_*.py explicitly so that
    # glob expansion doesn't silently drop files if cwd semantics change.
    cmd.extend(str(p) for p in Path("scripts").glob("run_l2_*.py"))
    cmd.extend(str(p) for p in Path("scripts").glob("render_l2_*.py"))

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    # ruff exits 0 on clean, 1 on findings
    if proc.returncode == 0:
        return
    pytest.fail(f"Dead code found in L2 surface:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")


def test_no_orphan_test_files_for_removed_modules() -> None:
    """Every tests/test_l2_*.py targets a live module or artifact path."""
    test_files = list(Path("tests").glob("test_l2_*.py"))
    assert test_files, "no L2 test files found — sanity check failed"
    # Each test file either imports a live research module or references
    # a results/ artifact path. A test file for a removed module would
    # fail to import and surface as a collection error elsewhere.
    for tf in test_files:
        text = tf.read_text(encoding="utf-8")
        has_import = "from research.microstructure" in text or "from tests." in text
        has_artifact = "results/" in text or "L2_" in text
        has_script_ref = "scripts/run_l2_" in text or "scripts/render_l2_" in text
        has_tooling_ref = "l2-" in text or "Makefile" in text
        anchored = has_import or has_artifact or has_script_ref or has_tooling_ref
        assert anchored, f"orphan test file: {tf}"


def test_python_executable_is_reachable() -> None:
    """Sanity — the python interpreter running pytest is on disk."""
    assert Path(sys.executable).exists()
