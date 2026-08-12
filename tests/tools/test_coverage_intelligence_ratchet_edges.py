# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Ratchet-edge falsifiers for the coverage intelligence authority.

These tests protect the measurement layer itself. They pin branch parsing,
critical-target absence, executable diff intersection, and machine-readable
report shape so a future coverage run cannot look green by losing evidence.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from tools.coverage import geosync_coverage_intelligence as gci


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
    rationale = "execution"
    """
)


def _targets(tmp_path: Path) -> gci.CoverageTargets:
    path = tmp_path / "coverage_targets.toml"
    path.write_text(TARGETS_TOML, encoding="utf-8")
    return gci.load_coverage_targets(path)


def _coverage_with_branches() -> str:
    return textwrap.dedent(
        """\
        <?xml version="1.0" ?>
        <coverage line-rate="1.0" branch-rate="0.5" version="7.0">
          <packages>
            <package name="execution">
              <classes>
                <class filename="execution/oms.py">
                  <lines>
                    <line number="1" hits="1"/>
                    <line number="2" hits="1" branch="true" condition-coverage="50% (1/2)"/>
                    <line number="3" hits="1" branch="true" condition-coverage="100% (2/2)"/>
                  </lines>
                </class>
              </classes>
            </package>
          </packages>
        </coverage>
        """
    )


def test_branch_coverage_is_computed_from_condition_coverage(tmp_path: Path) -> None:
    cov = tmp_path / "coverage.xml"
    cov.write_text(_coverage_with_branches(), encoding="utf-8")

    files, status = gci.parse_coverage_xml(cov, tmp_path)
    assert status.valid is True
    assert files[0].branches == 4
    assert files[0].branches_covered == 3
    assert files[0].branch_rate == pytest.approx(75.0)

    surfaces = gci.aggregate_surfaces(files, _targets(tmp_path))
    assert gci.global_branch_coverage(surfaces) == pytest.approx(75.0)


def test_critical_target_absent_from_evidence_fails_closed(tmp_path: Path) -> None:
    critical = tmp_path / "critical.toml"
    critical.write_text(
        textwrap.dedent(
            """
            [[targets]]
            path = "execution/oms.py"
            min_line_rate = 75.0
            """
        ),
        encoding="utf-8",
    )
    cov = tmp_path / "coverage.xml"
    cov.write_text(
        '<coverage><packages><package name="x"><classes>'
        '<class filename="execution/other.py"><lines>'
        '<line number="1" hits="1"/></lines></class>'
        "</classes></package></packages></coverage>",
        encoding="utf-8",
    )

    files, status = gci.parse_coverage_xml(cov, tmp_path)
    assert status.valid is True
    [result] = gci.evaluate_critical(files, critical)
    assert result.actual is None
    assert result.ok is False


def test_diff_coverage_counts_changed_executable_misses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = [
        gci.FileCoverage(
            path="execution/oms.py",
            statements=4,
            covered=2,
            branches=0,
            branches_covered=0,
            covered_lines=frozenset({1, 3}),
            line_rate=50.0,
            branch_rate=0.0,
        )
    ]
    monkeypatch.setattr(
        gci,
        "changed_python_lines",
        lambda base, repo_root: {"execution/oms.py": {1, 2, 3, 99}},
    )
    monkeypatch.setitem(gci._miss_lines, "execution/oms.py", {2, 4})

    diff = gci.diff_coverage(files, "origin/main", tmp_path, _targets(tmp_path))

    assert diff.applicable is True
    assert diff.total_changed == 3
    assert diff.covered_changed == 2
    assert diff.rate == pytest.approx(66.6666667)


def test_report_summary_preserves_machine_verdict_and_gate_shape(tmp_path: Path) -> None:
    surface = gci.SurfaceCoverage(
        name="execution",
        statements=10,
        covered=9,
        branches=4,
        branches_covered=3,
        line_rate=90.0,
        branch_rate=75.0,
        target_final=95.0,
        claim_risk="critical",
    )

    gci.write_reports(
        tmp_path,
        surfaces={"execution": surface},
        release_cov=90.0,
        branch_cov=75.0,
        risk_score=90.0,
        untested=["execution/ghost.py"],
        critical=[gci.CriticalResult("execution/oms.py", 75.0, None)],
        diff=gci.DiffCoverage(True, 3, 2),
        claims=[
            gci.ClaimResult(
                claim_id="claim-1",
                priority="P0",
                tier="ANCHORED",
                test_id="tests/x.py::test_x",
                test_present=False,
                test_passed=None,
            )
        ],
        verdict=gci.VERDICT_ASSISTED,
        evidence=gci.EvidenceStatus(True),
        gates={"release_90": True, "critical_surface": False, "diff_90": False},
    )

    summary = json.loads((tmp_path / "coverage_summary.json").read_text(encoding="utf-8"))
    assert summary["schema_version"] == "2.0"
    assert summary["verdict"] == gci.VERDICT_ASSISTED
    assert summary["gates"] == {
        "critical_surface": False,
        "diff_90": False,
        "release_90": True,
    }
    assert summary["critical"] == [
        {"actual": None, "ok": False, "path": "execution/oms.py", "required": 75.0}
    ]
    assert summary["diff_coverage"] == {
        "applicable": True,
        "changed_lines": 3,
        "covered_lines": 2,
        "rate": 66.67,
    }
