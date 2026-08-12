# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the coverage-ascent calibration planner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tools.coverage.calibrate_coverage_ascent as cca


def _surface(line: float, statements: int, risk: str, target: float) -> dict[str, Any]:
    return {
        "line_rate": line,
        "branch_rate": max(0.0, line - 5.0),
        "statements": statements,
        "target_final": target,
        "claim_risk": risk,
    }


def _summary(*, valid: bool = True, release: float = 85.03) -> dict[str, Any]:
    return {
        "verdict": "MACHINE_ASSISTED",
        "evidence_valid": valid,
        "release_line_coverage": release,
        "risk_weighted_score": 88.1,
        "untested_file_count": 14,
        "surfaces": {
            "backtest": _surface(68.55, 1000, "high", 98.0),
            "execution": _surface(87.74, 800, "high", 95.0),
            "analytics": _surface(75.99, 200, "medium", 90.0),
            "complete": _surface(100.0, 50, "low", 90.0),
        },
    }


def test_next_band_and_risk_weighted_ranking() -> None:
    plan = cca.build_plan(_summary(), (90.0, 92.0, 95.0, 97.0), max_surfaces=6)

    assert plan.next_global_band == 90.0
    assert plan.global_gap_to_next_band == 4.97
    assert [item.surface for item in plan.recommended_surfaces[:2]] == [
        "backtest",
        "execution",
    ]
    assert plan.recommended_surfaces[0].weighted_deficit == 885.0


def test_complete_surface_is_excluded() -> None:
    plan = cca.build_plan(_summary(), (90.0, 92.0, 95.0, 97.0), max_surfaces=6)

    assert "complete" not in {item.surface for item in plan.recommended_surfaces}


def test_invalid_evidence_is_rejected_by_default(tmp_path: Path) -> None:
    summary_path = tmp_path / "coverage_summary.json"
    summary_path.write_text(json.dumps(_summary(valid=False)), encoding="utf-8")

    rc = cca.main(["--summary", str(summary_path), "--out", str(tmp_path / "out")])

    assert rc == cca.EXIT_EVIDENCE_INVALID


def test_review_override_writes_plan(tmp_path: Path) -> None:
    summary_path = tmp_path / "coverage_summary.json"
    out_dir = tmp_path / "out"
    summary_path.write_text(json.dumps(_summary(valid=False)), encoding="utf-8")

    rc = cca.main(
        [
            "--summary",
            str(summary_path),
            "--out",
            str(out_dir),
            "--no-enforce-evidence",
        ]
    )

    assert rc == cca.EXIT_OK
    assert (out_dir / "coverage_calibration_plan.json").exists()
    assert (out_dir / "coverage_calibration_plan.md").exists()


def test_non_object_summary_is_rejected(tmp_path: Path) -> None:
    summary_path = tmp_path / "coverage_summary.json"
    summary_path.write_text(json.dumps(["bad-shape"]), encoding="utf-8")

    rc = cca.main(["--summary", str(summary_path), "--out", str(tmp_path / "out")])

    assert rc == cca.EXIT_EVIDENCE_INVALID
    assert not (tmp_path / "out" / "coverage_calibration_plan.json").exists()
