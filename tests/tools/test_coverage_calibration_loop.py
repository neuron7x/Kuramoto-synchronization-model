# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the deterministic coverage calibration loop."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from tools.coverage import coverage_calibration_loop as ccl
from tools.coverage.surface_contract import load_coverage_targets


TARGETS_TOML = textwrap.dedent(
    """
    [global]
    final_aspirational_gate = 98
    current_release_gate = 90
    diff_coverage_gate = 90

    [surfaces.execution]
    paths = ["execution/"]
    short_term = 80
    mid_term = 90
    final = 95
    claim_risk = "critical"
    rationale = "execution safety"

    [surfaces.analytics]
    paths = ["analytics/"]
    short_term = 70
    mid_term = 85
    final = 90
    claim_risk = "medium"
    rationale = "analytics reporting"
    """
)


def _targets(tmp_path: Path):
    path = tmp_path / "coverage_targets.toml"
    path.write_text(TARGETS_TOML, encoding="utf-8")
    return load_coverage_targets(path)


def _summary() -> dict[str, object]:
    return {
        "verdict": "MACHINE_ASSISTED",
        "evidence_valid": True,
        "release_line_coverage": 81.0,
        "risk_weighted_score": 79.5,
        "diff_coverage": {"applicable": True, "rate": 75.0},
        "surfaces": {
            "analytics": {
                "line_rate": 84.0,
                "branch_rate": 60.0,
                "statements": 400,
            },
            "execution": {
                "line_rate": 82.0,
                "branch_rate": 70.0,
                "statements": 900,
            },
        },
    }


def test_build_plan_prioritizes_critical_surface_deficit(tmp_path: Path) -> None:
    plan = ccl.build_calibration_plan(
        _summary(),
        _targets(tmp_path),
        stage="mid_term",
        limit=2,
    )

    assert plan.schema_version == "1.0"
    assert plan.global_release_deficit == pytest.approx(9.0)
    assert plan.diff_deficit == pytest.approx(15.0)
    assert [item.name for item in plan.top_actions] == ["execution", "analytics"]
    assert plan.top_actions[0].claim_risk == "critical"
    assert "branch/edge" in plan.top_actions[0].action


def test_stage_selection_changes_target_without_touching_observation(tmp_path: Path) -> None:
    short_plan = ccl.build_calibration_plan(
        _summary(),
        _targets(tmp_path),
        stage="short_term",
        limit=8,
    )
    final_plan = ccl.build_calibration_plan(
        _summary(),
        _targets(tmp_path),
        stage="final",
        limit=8,
    )

    short_execution = next(item for item in short_plan.top_actions if item.name == "execution")
    final_execution = next(item for item in final_plan.top_actions if item.name == "execution")

    assert short_execution.line_rate == final_execution.line_rate == pytest.approx(82.0)
    assert short_execution.target == pytest.approx(80.0)
    assert final_execution.target == pytest.approx(95.0)
    assert short_execution.deficit == pytest.approx(0.0)
    assert final_execution.deficit == pytest.approx(13.0)


def test_invalid_evidence_keeps_fail_closed_stop_rule(tmp_path: Path) -> None:
    summary = {**_summary(), "evidence_valid": False, "verdict": "HUMAN_REVIEW_ONLY"}

    plan = ccl.build_calibration_plan(summary, _targets(tmp_path), stage="mid_term", limit=8)

    assert plan.evidence_valid is False
    assert plan.verdict == "HUMAN_REVIEW_ONLY"
    assert plan.stop_rules[0].startswith("stop if evidence_valid is false")


def test_write_plan_emits_json_and_markdown_contracts(tmp_path: Path) -> None:
    plan = ccl.build_calibration_plan(
        _summary(),
        _targets(tmp_path),
        stage="mid_term",
        limit=1,
    )

    ccl.write_plan(plan, tmp_path)

    payload = json.loads((tmp_path / "calibration_plan.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "calibration_plan.md").read_text(encoding="utf-8")

    assert payload["schema_version"] == "1.0"
    assert payload["top_actions"][0]["name"] == "execution"
    assert "## Deterministic command" in markdown
    assert "python -m tools.coverage.geosync_coverage_intelligence" in markdown
