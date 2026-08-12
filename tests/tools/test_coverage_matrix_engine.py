# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path

from tools.coverage import coverage_matrix_engine as cme
from tools.coverage.surface_contract import CoverageTargets, SurfaceTarget


def _targets(tmp_path: Path) -> CoverageTargets:
    return CoverageTargets(
        source_path=tmp_path / "coverage_targets.toml",
        global_thresholds={
            "current_release_gate": 90.0,
            "diff_coverage_gate": 90.0,
            "final_aspirational_gate": 98.0,
        },
        surfaces={
            "execution": SurfaceTarget(
                paths=("src/geosync/execution",),
                short_term=75.0,
                mid_term=85.0,
                final=95.0,
                claim_risk="critical",
                rationale="orders and risk transitions",
            ),
            "api": SurfaceTarget(
                paths=("src/geosync/application/api",),
                short_term=65.0,
                mid_term=75.0,
                final=85.0,
                claim_risk="medium",
                rationale="operator interface",
            ),
        },
    )


def test_matrix_marks_critical_deficit_as_fail_and_carries_calibration_action(
    tmp_path: Path,
) -> None:
    summary = {
        "verdict": "MACHINE_ASSISTED",
        "evidence_valid": True,
        "release_line_coverage": 88.0,
        "diff_coverage": {"applicable": True, "rate": 91.0},
        "surfaces": {
            "execution": {"line_rate": 70.0, "branch_rate": 80.0},
            "api": {"line_rate": 78.0, "branch_rate": 76.0},
        },
    }
    plan = {
        "top_actions": [
            {
                "name": "execution",
                "action": "add guardrail tests for execution state transitions",
            }
        ]
    }

    matrix = cme.build_coverage_matrix(summary, _targets(tmp_path), plan=plan, stage="mid_term")

    assert matrix.release_state == "FAIL"
    assert matrix.diff_state == "PASS"
    assert matrix.rows[0].surface == "execution"
    assert matrix.rows[0].state == "FAIL"
    assert matrix.rows[0].action == "add guardrail tests for execution state transitions"


def test_matrix_marks_green_surfaces_as_pass_with_hold_action(tmp_path: Path) -> None:
    summary = {
        "verdict": "MACHINE_VERIFIED",
        "evidence_valid": True,
        "release_line_coverage": 96.0,
        "diff_coverage": {"applicable": False},
        "surfaces": {
            "execution": {"line_rate": 96.0, "branch_rate": 95.0},
            "api": {"line_rate": 86.0, "branch_rate": 85.0},
        },
    }

    matrix = cme.build_coverage_matrix(summary, _targets(tmp_path), plan={}, stage="final")

    assert matrix.release_state == "PASS"
    assert matrix.diff_state == "UNKNOWN"
    assert {row.surface: row.state for row in matrix.rows} == {
        "execution": "PASS",
        "api": "PASS",
    }
    assert all(row.action == "hold calibrated floor" for row in matrix.rows)


def test_matrix_invalid_evidence_overrides_surface_states(tmp_path: Path) -> None:
    summary = {
        "verdict": "HUMAN_REVIEW_ONLY",
        "evidence_valid": False,
        "release_line_coverage": 100.0,
        "diff_coverage": {"applicable": True, "rate": 100.0},
        "surfaces": {
            "execution": {"line_rate": 100.0, "branch_rate": 100.0},
            "api": {"line_rate": 100.0, "branch_rate": 100.0},
        },
    }

    matrix = cme.build_coverage_matrix(summary, _targets(tmp_path), plan={}, stage="mid_term")

    assert matrix.release_state == "UNKNOWN"
    assert matrix.diff_state == "UNKNOWN"
    assert {row.state for row in matrix.rows} == {"UNKNOWN"}


def test_write_matrix_emits_json_and_markdown(tmp_path: Path) -> None:
    summary = {
        "verdict": "MACHINE_ASSISTED",
        "evidence_valid": True,
        "release_line_coverage": 90.0,
        "diff_coverage": {"applicable": True, "rate": 90.0},
        "surfaces": {
            "execution": {"line_rate": 85.0, "branch_rate": 85.0},
            "api": {"line_rate": 75.0, "branch_rate": 75.0},
        },
    }
    matrix = cme.build_coverage_matrix(summary, _targets(tmp_path), plan={}, stage="mid_term")

    cme.write_matrix(matrix, tmp_path)

    payload = json.loads((tmp_path / "coverage_matrix.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "coverage_matrix.md").read_text(encoding="utf-8")
    assert payload["schema_version"] == "1.0"
    assert payload["rows"][0]["surface"] in {"execution", "api"}
    assert "| rank | state | surface |" in markdown
