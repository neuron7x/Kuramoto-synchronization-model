# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

from pathlib import Path

from tools.ci import pr_summary


def test_parse_coverage_extracts_rates(tmp_path: Path) -> None:
    report = tmp_path / "coverage.xml"
    report.write_text(
        """<coverage line-rate='0.95' branch-rate='0.83'><packages/></coverage>""",
        encoding="utf-8",
    )
    metrics = pr_summary._parse_coverage(report)
    assert metrics == {"line_rate": 95.0, "branch_rate": 83.0}


def test_build_summary_sets_risk_levels() -> None:
    stages = [pr_summary.StageStatus(name="stage-a", result="success")]
    release = {"passed": True, "negative_tests": {"degraded": {"passed": False}}}
    energy = {"passed": True, "nominal_free_energy": 1.2, "nominal_entropy": 0.4}
    summary = pr_summary.build_summary(stages, {"line_rate": 95.0}, release, energy)
    assert summary["risk_level"] == "normal"

    failure_stage = [pr_summary.StageStatus(name="stage-b", result="failure")]
    blocked = pr_summary.build_summary(failure_stage, {}, release, energy)
    assert blocked["risk_level"] == "blocked"
