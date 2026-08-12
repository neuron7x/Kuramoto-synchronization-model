# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Scenario tests for the coverage calibration loop."""

from __future__ import annotations

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

    [surfaces.backtest]
    paths = ["backtest/"]
    short_term = 75
    mid_term = 88
    final = 95
    claim_risk = "high"
    rationale = "research claims"

    [surfaces.api]
    paths = ["application/api/"]
    short_term = 70
    mid_term = 85
    final = 90
    claim_risk = "medium"
    rationale = "operator interface"
    """
)


def _targets(tmp_path: Path):
    path = tmp_path / "coverage_targets.toml"
    path.write_text(TARGETS_TOML, encoding="utf-8")
    return load_coverage_targets(path)


def _summary(
    surfaces: dict[str, dict[str, float | int]],
    *,
    release: float = 92.0,
    diff: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "verdict": "MACHINE_ASSISTED",
        "evidence_valid": True,
        "release_line_coverage": release,
        "risk_weighted_score": 91.5,
        "diff_coverage": {"applicable": True, "rate": 91.0} if diff is None else diff,
        "surfaces": surfaces,
    }


def test_all_green_scenario_emits_no_actions(tmp_path: Path) -> None:
    summary = _summary(
        {
            "execution": {"line_rate": 96.0, "branch_rate": 95.0, "statements": 900},
            "backtest": {"line_rate": 90.0, "branch_rate": 89.0, "statements": 500},
            "api": {"line_rate": 87.0, "branch_rate": 86.0, "statements": 300},
        },
        release=93.0,
    )

    plan = ccl.build_calibration_plan(summary, _targets(tmp_path), stage="mid_term", limit=8)

    assert plan.global_release_deficit == pytest.approx(0.0)
    assert plan.diff_deficit == pytest.approx(0.0)
    assert plan.top_actions == []


def test_dynamic_degradation_scenario_prioritizes_critical_execution(tmp_path: Path) -> None:
    summary = _summary(
        {
            "execution": {"line_rate": 70.0, "branch_rate": 70.0, "statements": 900},
            "backtest": {"line_rate": 80.0, "branch_rate": 78.0, "statements": 900},
            "api": {"line_rate": 72.0, "branch_rate": 72.0, "statements": 900},
        },
        release=82.0,
    )

    plan = ccl.build_calibration_plan(summary, _targets(tmp_path), stage="mid_term", limit=3)

    assert plan.global_release_deficit == pytest.approx(8.0)
    assert [item.name for item in plan.top_actions] == ["execution", "api", "backtest"]
    assert plan.top_actions[0].claim_risk == "critical"
    assert "first-principles" in plan.top_actions[0].action


def test_branch_only_regression_scenario_requests_edge_tests(tmp_path: Path) -> None:
    summary = _summary(
        {
            "execution": {"line_rate": 92.0, "branch_rate": 55.0, "statements": 400},
            "backtest": {"line_rate": 90.0, "branch_rate": 89.0, "statements": 300},
            "api": {"line_rate": 86.0, "branch_rate": 85.0, "statements": 200},
        }
    )

    plan = ccl.build_calibration_plan(summary, _targets(tmp_path), stage="mid_term", limit=8)

    assert [item.name for item in plan.top_actions] == ["execution"]
    assert plan.top_actions[0].deficit == pytest.approx(0.0)
    assert plan.top_actions[0].branch_deficit == pytest.approx(35.0)
    assert "branch/edge tests" in plan.top_actions[0].action


def test_non_applicable_diff_scenario_does_not_create_diff_debt(tmp_path: Path) -> None:
    summary = _summary(
        {"execution": {"line_rate": 91.0, "branch_rate": 91.0, "statements": 100}},
        diff={"applicable": False, "rate": 0.0},
    )

    plan = ccl.build_calibration_plan(summary, _targets(tmp_path), stage="mid_term", limit=8)

    assert plan.diff_actual is None
    assert plan.diff_deficit == pytest.approx(0.0)
    assert plan.top_actions == []


def test_unknown_surface_noise_is_ignored_and_limit_is_enforced(tmp_path: Path) -> None:
    summary = _summary(
        {
            "execution": {"line_rate": 80.0, "branch_rate": 80.0, "statements": 500},
            "backtest": {"line_rate": 89.0, "branch_rate": 89.0, "statements": 500},
            "untracked": {"line_rate": 0.0, "branch_rate": 0.0, "statements": 5000},
        }
    )

    plan = ccl.build_calibration_plan(summary, _targets(tmp_path), stage="mid_term", limit=1)

    assert len(plan.top_actions) == 1
    assert plan.top_actions[0].name == "execution"
    assert all(item.name != "untracked" for item in plan.top_actions)


def test_final_stage_scenario_expands_actions_after_mid_term_passes(tmp_path: Path) -> None:
    summary = _summary(
        {"execution": {"line_rate": 92.0, "branch_rate": 92.0, "statements": 400}}
    )

    mid_plan = ccl.build_calibration_plan(summary, _targets(tmp_path), stage="mid_term", limit=8)
    final_plan = ccl.build_calibration_plan(summary, _targets(tmp_path), stage="final", limit=8)

    assert mid_plan.top_actions == []
    assert [item.name for item in final_plan.top_actions] == ["execution"]
    assert final_plan.top_actions[0].target == pytest.approx(95.0)
    assert final_plan.top_actions[0].deficit == pytest.approx(3.0)
