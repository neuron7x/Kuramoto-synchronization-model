"""RVG-1 self-verification suite (protocol §10).

Proves the audit harness itself: formula correctness, fail-closed behaviour on
missing/zero-denominator evidence, threshold boundaries, and the recompute
cross-check (delta ≤ 0.01). These tests are the oracle for the oracle.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # register so dataclass forward-refs resolve
    spec.loader.exec_module(mod)
    return mod


rvg = _load("rvg_audit")
norm = _load("rvg_normalize_mutation")
verify = _load("rvg_verify_artifacts")


# --------------------------------------------------------------------------- #
# Fixtures — the §10.1 golden fixture
# --------------------------------------------------------------------------- #
def _write_coverage(path: Path, *, cl=80, ns=100, cb=70, nb=100, pct=75.0) -> Path:
    path.write_text(
        json.dumps(
            {
                "totals": {
                    "covered_lines": cl,
                    "num_statements": ns,
                    "covered_branches": cb,
                    "num_branches": nb,
                    "percent_covered": pct,
                }
            }
        )
    )
    return path


def _write_junit(path: Path, *, tests=10, failures=0, errors=0, skipped=0) -> Path:
    path.write_text(
        f'<testsuite tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}"></testsuite>'
    )
    return path


def _write_mutation(path: Path, *, killed=60, survived=20) -> Path:
    result = norm.normalize(tool="fixture", killed=killed, survived=survived)
    path.write_text(json.dumps(result))
    return path


def _full_verdict(tmp_path: Path, thresholds=None, **overrides):
    cov = _write_coverage(tmp_path / "coverage.json", **overrides.get("cov", {}))
    junit = _write_junit(tmp_path / "junit.xml", **overrides.get("junit", {}))
    mut = _write_mutation(tmp_path / "mutation.json", **overrides.get("mut", {}))
    (tmp_path / "sbom.json").write_text(
        json.dumps({"bomFormat": "CycloneDX", "components": [{"name": "pkg", "version": "1.0"}]})
    )
    (tmp_path / "ruff.json").write_text("[]")
    (tmp_path / "mypy.txt").write_text("Success: no issues found\n")
    (tmp_path / "manifest").write_text("0" * 64 + "  x\n")
    return rvg.compute_verdict(
        coverage_path=cov,
        junit_path=junit,
        mutation_path=mut,
        ruff_path=tmp_path / "ruff.json",
        mypy_path=tmp_path / "mypy.txt",
        pip_audit_path=None,
        osv_path=None,
        sbom_path=tmp_path / "sbom.json",
        thresholds=thresholds or rvg.Thresholds(),
        hash_manifest_present=True,
        repo="fixture",
        commit="deadbeef",
        timestamp_utc="1970-01-01T00:00:00Z",
        python_version="3.11.0",
    )


# --------------------------------------------------------------------------- #
# §10.1 Formula verification
# --------------------------------------------------------------------------- #
def test_golden_fixture_formulas(tmp_path):
    v = _full_verdict(tmp_path)
    assert v.fields["line_coverage"] == 80.00
    assert v.fields["branch_coverage"] == 70.00
    assert v.fields["mutation_score"] == 75.00
    assert v.fields["oracle_gap"] == -5.00
    assert v.fields["verified_test_strength"] == 70.00


def test_verified_test_strength_is_conservative_min(tmp_path):
    v = _full_verdict(tmp_path, cov={"cb": 94, "nb": 100}, mut={"killed": 61, "survived": 39})
    assert v.fields["branch_coverage"] == 94.00
    assert v.fields["mutation_score"] == 61.00
    assert v.fields["verified_test_strength"] == 61.00


def test_mutation_normalizer_formula():
    r = norm.normalize(tool="t", killed=60, survived=20)
    assert r["valid_mutants"] == 80
    assert r["mutation_score"] == 75.0


def test_timeout_not_killed_by_default():
    r = norm.normalize(tool="t", killed=60, survived=20, timeout=10)
    assert r["killed"] == 60
    assert r["valid_mutants"] == 80


def test_timeout_stable_counts_as_killed():
    r = norm.normalize(tool="t", killed=60, survived=20, timeout=10, timeout_stable=True)
    assert r["killed"] == 70
    assert r["valid_mutants"] == 90
    assert r["mutation_score"] == round(70 / 90 * 100, 2)
    assert r["timeout"] == 10  # still reported


# --------------------------------------------------------------------------- #
# §10.2 Fail-closed verification
# --------------------------------------------------------------------------- #
def test_missing_coverage_fails(tmp_path):
    junit = _write_junit(tmp_path / "junit.xml")
    mut = _write_mutation(tmp_path / "mutation.json")
    v = rvg.compute_verdict(
        coverage_path=tmp_path / "nope.json",
        junit_path=junit,
        mutation_path=mut,
        ruff_path=None, mypy_path=None, pip_audit_path=None, osv_path=None, sbom_path=None,
        thresholds=rvg.Thresholds(), hash_manifest_present=True,
        repo="x", commit="", timestamp_utc="", python_version="",
    )
    assert v.fields["verdict"] == "FAIL"
    assert any("coverage" in r for r in v.fail_reasons)


def test_zero_denominator_coverage_fails(tmp_path):
    cov = _write_coverage(tmp_path / "coverage.json", cb=0, nb=0)
    with pytest.raises(rvg.AuditError):
        rvg.coverage_metrics(json.loads(cov.read_text()))


def test_zero_valid_mutants_fails():
    with pytest.raises(rvg.AuditError):
        rvg.mutation_metric({"killed": 0, "survived": 0, "valid_mutants": 0})


def test_missing_sbom_fails(tmp_path):
    v2 = rvg.compute_verdict(
        coverage_path=_write_coverage(tmp_path / "c.json", cb=90, nb=100),
        junit_path=_write_junit(tmp_path / "j.xml"),
        mutation_path=_write_mutation(tmp_path / "m.json", killed=90, survived=10),
        ruff_path=None, mypy_path=None, pip_audit_path=None, osv_path=None,
        sbom_path=tmp_path / "absent.json",
        thresholds=rvg.Thresholds(), hash_manifest_present=True,
        repo="x", commit="", timestamp_utc="", python_version="",
    )
    assert any("sbom" in r for r in v2.fail_reasons)


def test_missing_hash_manifest_fails(tmp_path):
    v = rvg.compute_verdict(
        coverage_path=_write_coverage(tmp_path / "c.json", cb=90, nb=100),
        junit_path=_write_junit(tmp_path / "j.xml"),
        mutation_path=_write_mutation(tmp_path / "m.json", killed=90, survived=10),
        ruff_path=None, mypy_path=None, pip_audit_path=None, osv_path=None,
        sbom_path=None,
        thresholds=rvg.Thresholds(), hash_manifest_present=False,
        repo="x", commit="", timestamp_utc="", python_version="",
    )
    assert any("hash-manifest" in r for r in v.fail_reasons)


def test_failing_tests_fail_closed(tmp_path):
    v = _full_verdict(tmp_path, junit={"tests": 10, "failures": 1})
    assert v.fields["verdict"] == "FAIL"
    assert any("failing" in r for r in v.fail_reasons)


# --------------------------------------------------------------------------- #
# §10.3 Cross-check verification (recompute vs stored, delta ≤ 0.01)
# --------------------------------------------------------------------------- #
def test_cross_check_detects_tampered_percentage(tmp_path):
    v = _full_verdict(tmp_path)
    fields = dict(v.fields)
    fields["line_coverage"] = 99.0  # tamper, raw pair unchanged
    (tmp_path / "verdict.json").write_text(json.dumps(fields))
    with pytest.raises(verify.VerifyError):
        verify.cross_check_recompute(fields)


def test_cross_check_passes_on_honest_verdict(tmp_path):
    v = _full_verdict(tmp_path)
    checked = verify.cross_check_recompute(v.fields)
    assert "line_coverage" in checked and "branch_coverage" in checked
    assert "mutation_score" in checked and "test_pass_rate" in checked


def test_cross_check_verifies_derived_metrics(tmp_path):
    v = _full_verdict(tmp_path)
    checked = verify.cross_check_recompute(v.fields)
    assert "oracle_gap" in checked and "verified_test_strength" in checked


def test_metric_reported_disagreement_fails():
    m = rvg.Metric(value=75.0, numerator=60, denominator=80)
    m.cross_check(75.0, what="x")  # agrees
    with pytest.raises(rvg.AuditError):
        m.cross_check(80.0, what="x")  # reported disagrees


# --------------------------------------------------------------------------- #
# §3.7 Threshold boundaries
# --------------------------------------------------------------------------- #
def test_branch_exactly_at_threshold_passes(tmp_path):
    th = rvg.Thresholds(line_coverage=80, branch_coverage=85, mutation_score=75, oracle_gap=15)
    v = _full_verdict(tmp_path, cov={"cl": 80, "ns": 100, "cb": 85, "nb": 100},
                      mut={"killed": 75, "survived": 25}, thresholds=th)
    assert not any("branch_coverage" in r for r in v.fail_reasons)


def test_branch_just_below_threshold_fails(tmp_path):
    th = rvg.Thresholds(line_coverage=80, branch_coverage=85, mutation_score=75, oracle_gap=100)
    v = _full_verdict(tmp_path, cov={"cl": 80, "ns": 100, "cb": 84, "nb": 100},
                      mut={"killed": 75, "survived": 25}, thresholds=th)
    assert any("branch_coverage" in r for r in v.fail_reasons)


def test_oracle_gap_boundary(tmp_path):
    # branch 95, mutation 79 -> gap 16 > 15 -> fail
    th = rvg.Thresholds(line_coverage=80, branch_coverage=0, mutation_score=0, oracle_gap=15)
    v = _full_verdict(tmp_path, cov={"cl": 80, "ns": 100, "cb": 95, "nb": 100},
                      mut={"killed": 79, "survived": 21}, thresholds=th)
    assert v.fields["oracle_gap"] == 16.0
    assert any("oracle_gap" in r for r in v.fail_reasons)


def test_unknown_severity_not_promoted_to_high_critical(tmp_path):
    # PyPI advisories usually omit severity — must NOT be counted as high/critical.
    pa = tmp_path / "pip.json"
    pa.write_text(
        json.dumps(
            {"dependencies": [{"name": "x", "vulns": [{"id": "V1"}, {"id": "V2"}]}]}
        )
    )
    c = rvg.pip_audit_vulns(pa)
    assert c.high_critical == 0
    assert c.unknown == 2
    assert c.total == 2


def test_explicit_high_severity_counted(tmp_path):
    pa = tmp_path / "pip.json"
    pa.write_text(
        json.dumps(
            {
                "dependencies": [
                    {"name": "x", "vulns": [{"id": "V1", "severity": "high"}]},
                    {"name": "y", "vulns": [{"id": "V2", "severity": "critical"}]},
                    {"name": "z", "vulns": [{"id": "V3"}]},
                ]
            }
        )
    )
    c = rvg.pip_audit_vulns(pa)
    assert c.high_critical == 2
    assert c.unknown == 1


def test_unknown_severity_does_not_fail_gate(tmp_path):
    pa = tmp_path / "pip.json"
    pa.write_text(json.dumps({"dependencies": [{"name": "x", "vulns": [{"id": "V1"}]}]}))
    v = rvg.compute_verdict(
        coverage_path=_write_coverage(tmp_path / "c.json", cb=90, nb=100),
        junit_path=_write_junit(tmp_path / "j.xml"),
        mutation_path=_write_mutation(tmp_path / "m.json", killed=90, survived=10),
        ruff_path=None, mypy_path=None, pip_audit_path=pa, osv_path=None,
        sbom_path=None, thresholds=rvg.Thresholds(), hash_manifest_present=True,
        repo="x", commit="", timestamp_utc="", python_version="",
    )
    assert v.fields["pip_audit_high_critical"] == 0
    assert v.fields["pip_audit_unknown_severity"] == 1
    assert v.fields["unknown_severity_vulnerabilities"] == 1
    assert not any("supply-chain" in r for r in v.fail_reasons)


def test_high_vuln_fails(tmp_path):
    pa = tmp_path / "pip.json"
    pa.write_text(json.dumps({"dependencies": [
        {"name": "x", "vulns": [{"id": "V1", "severity": "high"}]}
    ]}))
    v = rvg.compute_verdict(
        coverage_path=_write_coverage(tmp_path / "c.json", cb=90, nb=100),
        junit_path=_write_junit(tmp_path / "j.xml"),
        mutation_path=_write_mutation(tmp_path / "m.json", killed=90, survived=10),
        ruff_path=None, mypy_path=None, pip_audit_path=pa, osv_path=None,
        sbom_path=None, thresholds=rvg.Thresholds(), hash_manifest_present=True,
        repo="x", commit="", timestamp_utc="", python_version="",
    )
    assert v.fields["pip_audit_high_critical"] == 1
    assert any("supply-chain" in r for r in v.fail_reasons)


# --------------------------------------------------------------------------- #
# End-to-end: main() writes artifacts and returns fail-closed exit code
# --------------------------------------------------------------------------- #
def test_main_emits_artifacts_and_exit_code(tmp_path):
    cov = _write_coverage(tmp_path / "coverage.json", cb=90, nb=100, cl=95, ns=100)
    junit = _write_junit(tmp_path / "junit.xml")
    mut = _write_mutation(tmp_path / "mutation.json", killed=90, survived=10)
    sbom = tmp_path / "sbom.json"
    sbom.write_text(
        json.dumps({"bomFormat": "CycloneDX", "components": [{"name": "pkg", "version": "1.0"}]})
    )
    manifest = tmp_path / "audit.hashes"
    manifest.write_text("0" * 64 + "  file\n")
    out_json = tmp_path / "RVG_VERDICT.json"
    out_md = tmp_path / "RVG_VERDICT.md"
    code = rvg.main([
        "--coverage", str(cov), "--junit", str(junit), "--mutation", str(mut),
        "--sbom", str(sbom), "--hash-manifest", str(manifest),
        "--out-json", str(out_json), "--out-md", str(out_md),
        "--repo", "geosync", "--commit", "abc", "--timestamp", "T", "--python-version", "3.11",
    ])
    assert code == 0
    data = json.loads(out_json.read_text())
    assert data["verdict"] == "PASS"
    assert data["verified_test_strength"] == 90.0
    assert out_md.read_text().startswith("# RVG VERDICT")


def test_reproducibility_diff_ignores_nondeterministic_fields():
    a = {"verdict": "PASS", "line_coverage": 90.0, "timestamp_utc": "t1", "commit": "c1"}
    b = {"verdict": "PASS", "line_coverage": 90.0, "timestamp_utc": "t2", "commit": "c2"}
    assert verify.diff_reproducibility(a, b) == []
    c = {"verdict": "PASS", "line_coverage": 91.0, "timestamp_utc": "t2", "commit": "c2"}
    assert verify.diff_reproducibility(a, c) == ["line_coverage"]
