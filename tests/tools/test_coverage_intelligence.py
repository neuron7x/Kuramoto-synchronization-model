# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsification suite for the Coverage Intelligence authority.

The instrument's job is to refuse a green verdict when the evidence behind it
is missing, empty, malformed, or stale, and to compute honest per-surface and
risk-weighted coverage. These tests attack each of those guarantees: if the
tool ever trusts bad evidence or inflates a number, one of them fails.
"""

from __future__ import annotations

import os
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

    [surfaces.analytics]
    paths = ["analytics/"]
    short_term = 75
    mid_term = 85
    final = 90
    claim_risk = "medium"
    rationale = "analytics"
    """
)

CRITICAL_TOML = textwrap.dedent(
    """
    [[targets]]
    path = "execution/oms.py"
    min_line_rate = 75.0
    """
)


def _coverage_xml(execution_hits: list[int], analytics_hits: list[int]) -> str:
    def lines(hits: list[int]) -> str:
        return "".join(
            f'<line number="{i + 1}" hits="{h}"/>' for i, h in enumerate(hits)
        )

    return textwrap.dedent(
        f"""\
        <?xml version="1.0" ?>
        <coverage line-rate="0.5" branch-rate="0.0" version="7.0">
          <packages>
            <package name="execution">
              <classes>
                <class filename="execution/oms.py"><lines>{lines(execution_hits)}</lines></class>
              </classes>
            </package>
            <package name="analytics">
              <classes>
                <class filename="analytics/x.py"><lines>{lines(analytics_hits)}</lines></class>
              </classes>
            </package>
          </packages>
        </coverage>
        """
    )


@pytest.fixture()
def targets(tmp_path: Path) -> gci.CoverageTargets:
    p = tmp_path / "targets.toml"
    p.write_text(TARGETS_TOML, encoding="utf-8")
    return gci.load_coverage_targets(p)


# --------------------------------------------------------------------------- #
# Evidence parsing — fail closed
# --------------------------------------------------------------------------- #
def test_missing_coverage_xml_is_invalid(tmp_path: Path) -> None:
    files, status = gci.parse_coverage_xml(tmp_path / "nope.xml")
    assert files == []
    assert status.valid is False
    assert any("missing" in r for r in status.reasons)


def test_empty_coverage_xml_is_invalid(tmp_path: Path) -> None:
    p = tmp_path / "cov.xml"
    p.write_text("   \n", encoding="utf-8")
    _, status = gci.parse_coverage_xml(p)
    assert status.valid is False
    assert any("empty" in r for r in status.reasons)


def test_malformed_coverage_xml_is_invalid(tmp_path: Path) -> None:
    p = tmp_path / "cov.xml"
    p.write_text("<coverage><not-closed>", encoding="utf-8")
    _, status = gci.parse_coverage_xml(p)
    assert status.valid is False
    assert any("malformed" in r for r in status.reasons)


def test_zero_statement_coverage_is_invalid(tmp_path: Path) -> None:
    p = tmp_path / "cov.xml"
    p.write_text(
        '<coverage><packages><package name="x"><classes>'
        '<class filename="execution/oms.py"><lines></lines></class>'
        "</classes></package></packages></coverage>",
        encoding="utf-8",
    )
    _, status = gci.parse_coverage_xml(p)
    assert status.valid is False


def test_valid_coverage_xml_parses_per_file(tmp_path: Path) -> None:
    p = tmp_path / "cov.xml"
    p.write_text(_coverage_xml([1, 1, 0, 1], [0, 0]), encoding="utf-8")
    files, status = gci.parse_coverage_xml(p)
    assert status.valid is True
    by_path = {f.path: f for f in files}
    oms = by_path["execution/oms.py"]
    assert oms.statements == 4
    assert oms.covered == 3
    assert oms.line_rate == pytest.approx(75.0)


# --------------------------------------------------------------------------- #
# Staleness — code newer than coverage = untrustworthy
# --------------------------------------------------------------------------- #
def test_staleness_detects_source_newer_than_coverage(tmp_path: Path) -> None:
    (tmp_path / "execution").mkdir()
    src = tmp_path / "execution" / "oms.py"
    src.write_text("x = 1\n", encoding="utf-8")
    cov = tmp_path / "cov.xml"
    cov.write_text(_coverage_xml([1, 1], [1, 1]), encoding="utf-8")
    files, _ = gci.parse_coverage_xml(cov)
    # Make coverage old and source new.
    old = 1_000.0
    os.utime(cov, (old, old))
    os.utime(src, (old + 10_000, old + 10_000))
    status = gci.check_staleness(files, cov, tmp_path, skew_seconds=2.0)
    assert status.valid is False
    assert any("stale" in r for r in status.reasons)


def test_staleness_passes_when_coverage_newer(tmp_path: Path) -> None:
    (tmp_path / "execution").mkdir()
    src = tmp_path / "execution" / "oms.py"
    src.write_text("x = 1\n", encoding="utf-8")
    cov = tmp_path / "cov.xml"
    cov.write_text(_coverage_xml([1, 1], [1, 1]), encoding="utf-8")
    files, _ = gci.parse_coverage_xml(cov)
    os.utime(src, (1_000.0, 1_000.0))
    os.utime(cov, (50_000.0, 50_000.0))
    status = gci.check_staleness(files, cov, tmp_path, skew_seconds=2.0)
    assert status.valid is True


# --------------------------------------------------------------------------- #
# Surface aggregation + scores
# --------------------------------------------------------------------------- #
def test_global_release_coverage_recomputed_from_lines(
    tmp_path: Path, targets: gci.CoverageTargets
) -> None:
    p = tmp_path / "cov.xml"
    # execution 3/4, analytics 0/2 => 3/6 = 50%, NOT the decorative root 0.5...
    p.write_text(_coverage_xml([1, 1, 0, 1], [0, 0]), encoding="utf-8")
    files, _ = gci.parse_coverage_xml(p)
    surfaces = gci.aggregate_surfaces(files, targets)
    assert surfaces["execution"].line_rate == pytest.approx(75.0)
    assert surfaces["analytics"].line_rate == pytest.approx(0.0)
    assert gci.global_release_coverage(surfaces) == pytest.approx(50.0)


def test_risk_weighting_favors_critical_surface(
    tmp_path: Path, targets: gci.CoverageTargets
) -> None:
    # Equal statements, execution(critical) fully covered, analytics(medium) zero.
    p = tmp_path / "cov.xml"
    p.write_text(_coverage_xml([1, 1], [0, 0]), encoding="utf-8")
    files, _ = gci.parse_coverage_xml(p)
    surfaces = gci.aggregate_surfaces(files, targets)
    risk = gci.risk_weighted_score(surfaces)
    plain = gci.global_release_coverage(surfaces)
    # Plain = 50%. Risk-weighted must be HIGHER because the covered surface
    # (execution) carries weight 4 vs analytics weight 2.
    assert risk > plain


def test_untested_files_flags_zero_coverage(
    tmp_path: Path, targets: gci.CoverageTargets
) -> None:
    p = tmp_path / "cov.xml"
    p.write_text(_coverage_xml([1, 1], [0, 0]), encoding="utf-8")
    files, _ = gci.parse_coverage_xml(p)
    assert gci.untested_files(files, targets) == ["analytics/x.py"]


def test_critical_below_threshold_is_flagged(tmp_path: Path) -> None:
    crit = tmp_path / "critical.toml"
    crit.write_text(CRITICAL_TOML, encoding="utf-8")
    p = tmp_path / "cov.xml"
    p.write_text(_coverage_xml([1, 0, 0, 0], [1, 1]), encoding="utf-8")  # oms 25%
    files, _ = gci.parse_coverage_xml(p)
    results = gci.evaluate_critical(files, crit)
    oms = next(r for r in results if r.path == "execution/oms.py")
    assert oms.actual == pytest.approx(25.0)
    assert oms.ok is False


# --------------------------------------------------------------------------- #
# Claim falsifier matrix
# --------------------------------------------------------------------------- #
CLAIMS_YAML = textwrap.dedent(
    """
    schema_version: 3
    claims:
      - id: anchored-claim
        priority: P0
        tier: ANCHORED
        falsifier:
          test_id: tests/x.py::test_anchored
      - id: no-test-claim
        priority: P1
        tier: ANCHORED
        falsifier:
          test_id: tests/y.py::test_missing
    """
)

JUNIT_PASS = (
    '<testsuites><testsuite>'
    '<testcase classname="tests.x" name="test_anchored"/>'
    "</testsuite></testsuites>"
)
JUNIT_FAIL = (
    '<testsuites><testsuite>'
    '<testcase classname="tests.x" name="test_anchored"><failure/></testcase>'
    "</testsuite></testsuites>"
)


def test_claim_matrix_marks_present_and_passing(tmp_path: Path) -> None:
    claims_p = tmp_path / "CLAIMS.yaml"
    claims_p.write_text(CLAIMS_YAML, encoding="utf-8")
    junit_p = tmp_path / "junit.xml"
    junit_p.write_text(JUNIT_PASS, encoding="utf-8")
    results, _ = gci.claim_matrix(claims_p, junit_p)
    by_id = {c.claim_id: c for c in results}
    assert by_id["anchored-claim"].test_present is True
    assert by_id["anchored-claim"].complete is True
    # The second claim's falsifier test is absent from junit.
    assert by_id["no-test-claim"].test_present is False
    assert by_id["no-test-claim"].complete is False


def test_claim_matrix_marks_failing_test_incomplete(tmp_path: Path) -> None:
    claims_p = tmp_path / "CLAIMS.yaml"
    claims_p.write_text(CLAIMS_YAML, encoding="utf-8")
    junit_p = tmp_path / "junit.xml"
    junit_p.write_text(JUNIT_FAIL, encoding="utf-8")
    results, _ = gci.claim_matrix(claims_p, junit_p)
    anchored = next(c for c in results if c.claim_id == "anchored-claim")
    assert anchored.test_present is True
    assert anchored.test_passed is False
    assert anchored.complete is False


# --------------------------------------------------------------------------- #
# End-to-end verdict + exit codes via main()
# --------------------------------------------------------------------------- #
def _write_env(tmp_path: Path, exec_hits: list[int], ana_hits: list[int]) -> dict[str, str]:
    cov = tmp_path / "cov.xml"
    cov.write_text(_coverage_xml(exec_hits, ana_hits), encoding="utf-8")
    targets_p = tmp_path / "targets.toml"
    targets_p.write_text(TARGETS_TOML, encoding="utf-8")
    crit = tmp_path / "critical.toml"
    crit.write_text(CRITICAL_TOML, encoding="utf-8")
    claims_p = tmp_path / "CLAIMS.yaml"
    claims_p.write_text(CLAIMS_YAML, encoding="utf-8")
    junit_p = tmp_path / "junit.xml"
    junit_p.write_text(JUNIT_PASS, encoding="utf-8")
    return {
        "cov": str(cov),
        "targets": str(targets_p),
        "critical": str(crit),
        "claims": str(claims_p),
        "junit": str(junit_p),
        "out": str(tmp_path / "reports"),
    }


def _argv(env: dict[str, str], *extra: str) -> list[str]:
    return [
        "--coverage",
        env["cov"],
        "--junit",
        env["junit"],
        "--targets",
        env["targets"],
        "--critical",
        env["critical"],
        "--claims",
        env["claims"],
        "--out",
        env["out"],
        "--no-check-staleness",
        "--diff-base",
        "HEAD",
        *extra,
    ]


def test_main_fail_closed_exit_3_on_missing(tmp_path: Path) -> None:
    env = _write_env(tmp_path, [1, 1], [1, 1])
    env["cov"] = str(tmp_path / "absent.xml")
    rc = gci.main(_argv(env))
    assert rc == gci.EXIT_EVIDENCE_INVALID


def test_main_exit_1_when_release_gate_unmet(tmp_path: Path) -> None:
    env = _write_env(tmp_path, [1, 0], [0, 0])  # 1/4 = 25% global
    rc = gci.main(_argv(env, "--enforce-release-90"))
    assert rc == gci.EXIT_GATE_FAILED


def test_main_exit_0_and_verdict_files_written(tmp_path: Path) -> None:
    env = _write_env(tmp_path, [1, 1, 1, 1], [1, 1, 1, 1])  # 100%
    rc = gci.main(_argv(env, "--enforce-release-90", "--enforce-critical"))
    assert rc == gci.EXIT_OK
    out = Path(env["out"])
    for name in (
        "coverage_summary.json",
        "coverage_gap_map.md",
        "risk_weighted_coverage.json",
        "claim_test_matrix.json",
        "next_tests.md",
    ):
        assert (out / name).exists(), name


def test_main_exit_2_on_incomplete_claims_when_enforced(tmp_path: Path) -> None:
    env = _write_env(tmp_path, [1, 1, 1, 1], [1, 1, 1, 1])
    # junit only covers anchored-claim; no-test-claim (P1/ANCHORED) is missing.
    rc = gci.main(_argv(env, "--enforce-claims"))
    assert rc == gci.EXIT_CLAIMS_INCOMPLETE


def test_verdict_human_review_only_written_on_bad_evidence(tmp_path: Path) -> None:
    import json

    env = _write_env(tmp_path, [1, 1], [1, 1])
    env["cov"] = str(tmp_path / "absent.xml")
    gci.main(_argv(env))
    summary = json.loads((Path(env["out"]) / "coverage_summary.json").read_text())
    assert summary["verdict"] == gci.VERDICT_HUMAN
    assert summary["evidence_valid"] is False


# --------------------------------------------------------------------------- #
# Multi-source-root path reconstruction (regression: PR #916 shipped a gate
# whose fixtures used repo-relative filenames, while the real release_90
# coverage.xml — generated with twelve top-level `source` dirs — emits each
# filename *relative to its matched source root* (`execution/oms.py` written
# as `oms.py`). The gate then matched nothing: all critical targets read None
# and 87% of files fell out of every surface. These tests pin the real format.
# --------------------------------------------------------------------------- #
def _multisource_xml(filename: str, hits: list[int], sources: list[str]) -> str:
    line_xml = "".join(f'<line number="{i + 1}" hits="{h}"/>' for i, h in enumerate(hits))
    src_xml = "".join(f"<source>{s}</source>" for s in sources)
    return textwrap.dedent(
        f"""\
        <?xml version="1.0" ?>
        <coverage line-rate="0.5" branch-rate="0.0" version="7.0">
          <sources>{src_xml}</sources>
          <packages>
            <package name="x">
              <classes>
                <class filename="{filename}"><lines>{line_xml}</lines></class>
              </classes>
            </package>
          </packages>
        </coverage>
        """
    )


def test_source_root_stripped_filename_is_reattached(tmp_path: Path) -> None:
    # coverage collapsed execution/oms.py -> oms.py under multiple source roots.
    (tmp_path / "execution").mkdir()
    (tmp_path / "execution" / "oms.py").write_text("a\nb\nc\nd\n", encoding="utf-8")
    cov = tmp_path / "cov.xml"
    cov.write_text(
        _multisource_xml(
            "oms.py", [1, 1, 0, 1], sources=[str(tmp_path / "core"), str(tmp_path / "execution")]
        ),
        encoding="utf-8",
    )
    files, status = gci.parse_coverage_xml(cov, tmp_path)
    assert status.valid is True
    assert [f.path for f in files] == ["execution/oms.py"]


def test_single_source_filename_is_trusted_as_is(tmp_path: Path) -> None:
    # One source root => already repo-relative; no reconstruction, no disk probe.
    cov = tmp_path / "cov.xml"
    cov.write_text(
        _multisource_xml("execution/oms.py", [1, 1], sources=[str(tmp_path)]),
        encoding="utf-8",
    )
    files, _ = gci.parse_coverage_xml(cov, tmp_path)
    assert [f.path for f in files] == ["execution/oms.py"]


def test_ambiguous_collapse_resolved_by_physical_length(tmp_path: Path) -> None:
    # security/tls.py exists under BOTH core/ and application/. The measured
    # class references line 5; the short application/ file (3 lines) cannot
    # carry it, so the long core/ file must be the real one — alphabetical
    # tie-break ("application" first) would have been wrong.
    for root, length in (("application", 3), ("core", 9)):
        d = tmp_path / root / "security"
        d.mkdir(parents=True)
        (d / "tls.py").write_text("\n".join("x" for _ in range(length)) + "\n", encoding="utf-8")
    cov = tmp_path / "cov.xml"
    cov.write_text(
        _multisource_xml(
            "security/tls.py",
            [1, 1, 1, 1, 0],  # last referenced line number = 5
            sources=[str(tmp_path / "application"), str(tmp_path / "core")],
        ),
        encoding="utf-8",
    )
    files, _ = gci.parse_coverage_xml(cov, tmp_path)
    assert [f.path for f in files] == ["core/security/tls.py"]


def test_unresolvable_collapse_fails_closed_to_unprefixed(tmp_path: Path) -> None:
    # No source root contains the file on disk => do not invent a path.
    cov = tmp_path / "cov.xml"
    cov.write_text(
        _multisource_xml(
            "ghost.py", [1, 0], sources=[str(tmp_path / "core"), str(tmp_path / "execution")]
        ),
        encoding="utf-8",
    )
    files, _ = gci.parse_coverage_xml(cov, tmp_path)
    assert [f.path for f in files] == ["ghost.py"]
