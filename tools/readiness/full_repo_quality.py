# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""QA-001 whole-repository quality report.

The PR gate (``python-quality``) runs ruff/black/mypy on *changed* files only,
so quality drift can accumulate in untouched modules invisibly. This generator
sweeps the *whole* repository with ruff and black and records the real counts —
honest evidence, not a rubber stamp. It does NOT mutate any file.

Run: ``python -m tools.readiness.full_repo_quality``. The artifact is
deterministic (sorted file lists, no wall-clock) so its SHA-256 is stable.
Exit code mirrors cleanliness (0 = repo-wide clean, 1 = drift present) so the
report-only CI lane surfaces the number without blocking.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

ARTIFACT = Path("governance/evidence/qa001_full_repo_quality_report.json")
_RUFF_SUMMARY = re.compile(r"Found (\d+) error", re.IGNORECASE)
_BLACK_SUMMARY = re.compile(r"(\d+) files? would be reformatted")


def _tool(name: str) -> str:
    local = Path(".venv/bin") / name
    if local.exists():
        return str(local)
    resolved = shutil.which(name)
    if resolved is None:  # pragma: no cover - environment without the linter
        raise RuntimeError(f"required quality tool not found on PATH: {name}")
    return resolved


def _ruff_sweep() -> dict[str, Any]:
    proc = subprocess.run(
        [_tool("ruff"), "check", "."],
        capture_output=True,
        text=True,
        check=False,
    )
    match = _RUFF_SUMMARY.search(proc.stdout + proc.stderr)
    count = int(match.group(1)) if match else 0
    return {"tool": "ruff", "scope": "repository", "error_count": count, "clean": count == 0}


def _black_sweep() -> dict[str, Any]:
    proc = subprocess.run(
        [_tool("black"), "--check", "."],
        capture_output=True,
        text=True,
        check=False,
    )
    match = _BLACK_SUMMARY.search(proc.stdout + proc.stderr)
    count = int(match.group(1)) if match else 0
    return {"tool": "black", "scope": "repository", "reformat_count": count, "clean": count == 0}


def build_report() -> dict[str, Any]:
    ruff = _ruff_sweep()
    black = _black_sweep()
    clean = bool(ruff["clean"] and black["clean"])
    return {
        "artifact": "qa001_full_repo_quality_report",
        "readiness_entry": "QA-001",
        "schema": "readiness.evidence.v1",
        "gap": (
            "python-quality PR gate lints changed files only; this report sweeps "
            "the whole repository so accumulated drift in untouched modules is visible."
        ),
        "sweeps": [ruff, black],
        "repo_wide_clean": clean,
        "residual_debt": {
            "ruff_errors": ruff["error_count"],
            "black_reformats": black["reformat_count"],
            "note": (
                "Residual repo-wide lint debt is now SURFACED and CI-retained "
                "(report-only). Zeroing it is tracked separately; closing QA-001 "
                "establishes the missing whole-repo evidence, not a clean bill."
            ),
        },
    }


def main() -> int:
    report = build_report()
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"repo_wide_clean": report["repo_wide_clean"], "path": str(ARTIFACT)}))
    return 0 if report["repo_wide_clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
