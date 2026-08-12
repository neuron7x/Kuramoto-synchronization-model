"""Task 1 · Deterministic replay audit.

Runs `scripts/run_l2_full_cycle.py` twice and verifies every stage
produces the bit-identical artifact (SHA-256 match). This is the
foundational coherence gate: a divergent second run proves hidden
non-determinism that would silently invalidate downstream claims.

Marked `slow`: skipped unless `L2_DETERMINISTIC_REPLAY=1` is set in
the environment. The test is ~170 s per run (two full cycles).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_DATA_DIR = Path("data/binance_l2_perp")
_REPO_ROOT = Path.cwd()


def _full_cycle_available() -> bool:
    if not _DATA_DIR.exists():
        return False
    return os.environ.get("L2_DETERMINISTIC_REPLAY") == "1"


@pytest.mark.skipif(
    not _full_cycle_available(),
    reason="deterministic replay disabled (set L2_DETERMINISTIC_REPLAY=1 to enable)",
)
def test_full_cycle_runs_are_bit_identical(tmp_path: Path) -> None:
    """Two independent cycle runs must produce identical SHA-256 for every stage."""

    def run_one(manifest_path: Path) -> dict[str, Any]:
        cmd = [
            sys.executable,
            "scripts/run_l2_full_cycle.py",
            "--data-dir",
            str(_DATA_DIR),
            "--manifest",
            str(manifest_path),
            "--skip-figures",
            "--log-level",
            "WARNING",
        ]
        proc = subprocess.run(
            cmd,
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(_REPO_ROOT), "PATH": ""},
        )
        assert proc.returncode == 0, f"cycle failed: {proc.stderr[-2000:]}"
        with manifest_path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        return data

    m_a = run_one(tmp_path / "a.json")
    m_b = run_one(tmp_path / "b.json")

    stages_a = {s["name"]: s["sha256"] for s in m_a["stages"]}
    stages_b = {s["name"]: s["sha256"] for s in m_b["stages"]}
    assert stages_a.keys() == stages_b.keys(), "stage set drift between runs"
    mismatches = [k for k in stages_a if stages_a[k] != stages_b[k]]
    assert not mismatches, f"non-deterministic stages: {mismatches}"
