# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsification suite for the silent-procedure ratchet.

The gate's claim is that it can see the shape the numeric fail-open gate cannot: a
procedure typed ``-> None`` whose broad ``except`` neither re-raises nor reports, so the
caller cannot tell "done" from "did not happen". These tests plant that shape and demand
a RED. A ratchet that cannot go red is a comment.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "ci" / "check_silent_procedures.py"


def _gate():
    spec = importlib.util.spec_from_file_location("_silentproc", GATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_silentproc"] = mod
    spec.loader.exec_module(mod)
    return mod


def _scan(root: Path) -> list[str]:
    mod = _gate()
    mod.REPO_ROOT = root
    mod.SCAN_ROOT = root / "geosync"
    return mod.find_silent_procedures()


def _write(root: Path, body: str) -> None:
    pkg = root / "geosync" / "execution"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "m.py").write_text(body, encoding="utf-8")


def test_the_live_tree_holds() -> None:
    proc = subprocess.run([sys.executable, str(GATE)], cwd=REPO_ROOT,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_a_swallowing_procedure_is_caught(tmp_path: Path) -> None:
    """POSITIVE CONTROL: the reconcile defect, in miniature."""
    _write(tmp_path, "def reconcile(ctx) -> None:\n"
                     "    try:\n        ctx.read()\n"
                     "    except Exception:\n        log('x')\n        return\n")
    assert any("reconcile" in h for h in _scan(tmp_path))


def test_a_procedure_that_reraises_is_not_caught(tmp_path: Path) -> None:
    """NEGATIVE CONTROL: the failure stays a failure -- nothing to report."""
    _write(tmp_path, "def reconcile(ctx) -> None:\n"
                     "    try:\n        ctx.read()\n"
                     "    except Exception:\n        log('x')\n        raise\n")
    assert _scan(tmp_path) == []


def test_a_measurer_is_out_of_scope(tmp_path: Path) -> None:
    """A function that RETURNS a value is the numeric gate's job: None is distinguishable."""
    _write(tmp_path, "def measure(ctx) -> float:\n"
                     "    try:\n        return ctx.read()\n"
                     "    except Exception:\n        return 0.5\n")
    assert _scan(tmp_path) == []


def test_a_narrow_except_is_not_a_silent_procedure(tmp_path: Path) -> None:
    """A handler that names its failure has already made a judgement about it."""
    _write(tmp_path, "def reconcile(ctx) -> None:\n"
                     "    try:\n        ctx.read()\n"
                     "    except ValueError:\n        return\n")
    assert _scan(tmp_path) == []


def test_capital_surfaces_are_flagged() -> None:
    mod = _gate()
    assert "geosync/execution/" in mod.CAPITAL_SURFACES
    assert "geosync/risk/" in mod.CAPITAL_SURFACES
