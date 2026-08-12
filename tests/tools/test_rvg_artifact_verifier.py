"""RVG-1 artifact-verifier + verdict-assertion suite (protocol P1-3/P1-5/P1-7).

Regression coverage for the four Codex review defects:

  * hash manifest must recompute real digests and reject a tampered/unbound
    verdict (P1-3),
  * an empty CycloneDX SBOM is not evidence (P2-1),
  * `tool: none` / zero-mutant mutation is fail-closed unless explicitly marked
    bootstrap_report_only (P1-2),
  * the verdict assertion enforces an explicit bootstrap/enforce mode (P1-5).
"""

from __future__ import annotations

import hashlib
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
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load order matters: rvg_assert_verdict does `import rvg_verify_artifacts`, so
# the verifier must be registered in sys.modules first. We deliberately do NOT
# put tools/ on sys.path — that would shadow the top-level `governance` package
# with tools/governance and break unrelated tests sharing the pytest session.
rvg = _load("rvg_audit")
norm = _load("rvg_normalize_mutation")
verify = _load("rvg_verify_artifacts")
assert_mod = _load("rvg_assert_verdict")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(root: Path, files: list[Path], *, name: str = "audit.hashes") -> Path:
    """sha256sum-style manifest with paths relative to `root`."""
    manifest = root / name
    lines = [f"{_sha256(p)}  {p.relative_to(root)}" for p in files]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def _sound_verdict_fields(*, verdict: str = "FAIL") -> dict:
    """A recompute-consistent verdict body (bootstrap mutation, real SBOM)."""
    return {
        "repo": "x",
        "verdict": verdict,
        "fail_reasons": [] if verdict == "PASS" else ["line_coverage 80.0 < 90"],
        "line_coverage": 80.0,
        "line_coverage_raw": [80, 100],
        "branch_coverage": 90.0,
        "branch_coverage_raw": [90, 100],
        "test_pass_rate": 100.0,
        "test_pass_rate_raw": [10, 10],
        "mutation_bootstrap_report_only": True,
        "mutation_tool": "none",
        "sbom_present": True,
        "hash_manifest_present": True,
    }


def _lay_down_verdict(root: Path, fields: dict) -> tuple[Path, Path]:
    """Write verdict + a manifest that covers it; return (verdict, manifest)."""
    verdict_path = root / "RVG_VERDICT.json"
    verdict_path.write_text(json.dumps(fields, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = _write_manifest(root, [verdict_path])
    return verdict_path, manifest


# --------------------------------------------------------------------------- #
# P1-3 — hash manifest recomputes real digests
# --------------------------------------------------------------------------- #
def test_valid_manifest_passes(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("hello")
    verdict = tmp_path / "RVG_VERDICT.json"
    verdict.write_text("{}")
    manifest = _write_manifest(tmp_path, [a, verdict])
    verify.verify_hash_manifest(verdict, manifest, root=tmp_path)  # no raise


def test_hash_manifest_recomputes_verdict_digest(tmp_path):
    verdict = tmp_path / "RVG_VERDICT.json"
    verdict.write_text(json.dumps({"verdict": "PASS"}))
    manifest = _write_manifest(tmp_path, [verdict])
    # The digest in the manifest is the real sha256 of the verdict file.
    line = manifest.read_text().strip().split()
    assert line[0] == _sha256(verdict)
    verify.verify_hash_manifest(verdict, manifest, root=tmp_path)


def test_hash_manifest_rejects_tampered_verdict(tmp_path):
    verdict = tmp_path / "RVG_VERDICT.json"
    verdict.write_text(json.dumps({"verdict": "FAIL"}))
    manifest = _write_manifest(tmp_path, [verdict])
    verdict.write_text(json.dumps({"verdict": "PASS"}))  # tamper AFTER hashing
    with pytest.raises(verify.VerifyError, match="digest mismatch"):
        verify.verify_hash_manifest(verdict, manifest, root=tmp_path)


def test_hash_manifest_rejects_wrong_digest(tmp_path):
    verdict = tmp_path / "RVG_VERDICT.json"
    verdict.write_text("payload")
    manifest = tmp_path / "audit.hashes"
    manifest.write_text("0" * 64 + "  RVG_VERDICT.json\n")
    with pytest.raises(verify.VerifyError, match="digest mismatch"):
        verify.verify_hash_manifest(verdict, manifest, root=tmp_path)


def test_hash_manifest_rejects_missing_file(tmp_path):
    verdict = tmp_path / "RVG_VERDICT.json"
    verdict.write_text("payload")
    manifest = tmp_path / "audit.hashes"
    manifest.write_text(f"{_sha256(verdict)}  RVG_VERDICT.json\n{'a' * 64}  gone.txt\n")
    with pytest.raises(verify.VerifyError, match="missing file"):
        verify.verify_hash_manifest(verdict, manifest, root=tmp_path)


def test_hash_manifest_rejects_missing_verdict_entry(tmp_path):
    verdict = tmp_path / "RVG_VERDICT.json"
    verdict.write_text("payload")
    other = tmp_path / "other.txt"
    other.write_text("x")
    manifest = _write_manifest(tmp_path, [other])  # verdict NOT covered
    with pytest.raises(verify.VerifyError, match="verdict not covered"):
        verify.verify_hash_manifest(verdict, manifest, root=tmp_path)


def test_hash_manifest_rejects_malformed_line(tmp_path):
    verdict = tmp_path / "RVG_VERDICT.json"
    verdict.write_text("x")
    manifest = tmp_path / "audit.hashes"
    manifest.write_text("not-a-hash RVG_VERDICT.json\n")
    with pytest.raises(verify.VerifyError, match="malformed"):
        verify.verify_hash_manifest(verdict, manifest, root=tmp_path)


def test_hash_manifest_rejects_path_traversal(tmp_path):
    verdict = tmp_path / "RVG_VERDICT.json"
    verdict.write_text("x")
    manifest = tmp_path / "audit.hashes"
    manifest.write_text(f"{_sha256(verdict)}  RVG_VERDICT.json\n{'a' * 64}  ../../etc/passwd\n")
    with pytest.raises(verify.VerifyError, match="escapes root"):
        verify.verify_hash_manifest(verdict, manifest, root=tmp_path)


def test_hash_manifest_skips_its_own_stale_self_entry(tmp_path):
    # sha256sum writes the manifest while listing it, so the self-entry hash is
    # intrinsically stale. It must be skipped, not fail the verify.
    verdict = tmp_path / "RVG_VERDICT.json"
    verdict.write_text("x")
    manifest = tmp_path / "audit.hashes"
    manifest.write_text(
        f"{_sha256(verdict)}  RVG_VERDICT.json\n{'f' * 64}  audit.hashes\n"
    )
    verify.verify_hash_manifest(verdict, manifest, root=tmp_path)  # no raise


# --------------------------------------------------------------------------- #
# P1-1 — coverage.json raw fields drive line/branch metrics
# --------------------------------------------------------------------------- #
def test_coverage_totals_fields_drive_metrics():
    cov = {
        "totals": {
            "covered_lines": 437,
            "num_statements": 594,
            "covered_branches": 153,
            "num_branches": 220,
        }
    }
    line, branch = rvg.coverage_metrics(cov)
    assert (line.numerator, line.denominator) == (437, 594)
    assert line.value == round(437 / 594 * 100, 2)
    assert (branch.numerator, branch.denominator) == (153, 220)
    assert branch.value == round(153 / 220 * 100, 2)


def test_coverage_missing_branch_counts_fails():
    with pytest.raises(rvg.AuditError, match="num_branches|covered_branches"):
        rvg.coverage_metrics({"totals": {"covered_lines": 90, "num_statements": 100}})


# --------------------------------------------------------------------------- #
# P2-1 — empty SBOM is not evidence
# --------------------------------------------------------------------------- #
def test_missing_sbom_is_not_present(tmp_path):
    assert rvg.sbom_present(tmp_path / "absent.json") is False


def test_invalid_json_sbom_is_not_present(tmp_path):
    p = tmp_path / "sbom.json"
    p.write_text("{not json")
    assert rvg.sbom_present(p) is False


def test_empty_sbom_is_not_present(tmp_path):
    p = tmp_path / "sbom.json"
    p.write_text(json.dumps({"bomFormat": "CycloneDX", "components": []}))
    assert rvg.sbom_present(p) is False


def test_real_sbom_with_component_is_present(tmp_path):
    p = tmp_path / "sbom.json"
    p.write_text(
        json.dumps({"bomFormat": "CycloneDX", "components": [{"name": "numpy", "version": "2.0"}]})
    )
    assert rvg.sbom_present(p) is True


# --------------------------------------------------------------------------- #
# P1-2 — mutation evidence fail-closed / bootstrap
# --------------------------------------------------------------------------- #
def test_mutation_none_zero_mutants_is_fail_closed():
    with pytest.raises(rvg.AuditError, match="valid_mutants = 0"):
        rvg.mutation_metric(norm.normalize(tool="none", killed=0, survived=0))


def test_real_mutation_json_requires_valid_mutants_positive():
    real = norm.normalize(tool="mutmut", killed=90, survived=10)
    assert real["tool"] == "mutmut"
    assert real["valid_mutants"] == 100
    m = rvg.mutation_metric(real)
    assert m.value == 90.0


def test_bootstrap_report_claims_no_score():
    r = norm.bootstrap_report()
    assert r["bootstrap_report_only"] is True
    assert r["mutation_score"] is None
    assert r["valid_mutants"] == 0


def test_bootstrap_mutation_is_non_enforcing_not_failclosed(tmp_path):
    # A bootstrap mutation record must NOT add a mutation fail-reason.
    cov = tmp_path / "c.json"
    cov.write_text(
        json.dumps({"totals": {"covered_lines": 95, "num_statements": 100,
                               "covered_branches": 90, "num_branches": 100}})
    )
    junit = tmp_path / "j.xml"
    junit.write_text('<testsuite tests="5" failures="0" errors="0" skipped="0"></testsuite>')
    mut = tmp_path / "m.json"
    mut.write_text(json.dumps(norm.bootstrap_report()))
    sbom = tmp_path / "s.json"
    sbom.write_text(json.dumps({"bomFormat": "CycloneDX", "components": [{"name": "p"}]}))
    v = rvg.compute_verdict(
        coverage_path=cov, junit_path=junit, mutation_path=mut,
        ruff_path=None, mypy_path=None, pip_audit_path=None, osv_path=None,
        sbom_path=sbom, thresholds=rvg.Thresholds(), hash_manifest_present=True,
        repo="x", commit="", timestamp_utc="", python_version="",
    )
    assert v.fields["mutation_bootstrap_report_only"] is True
    assert "mutation_score" not in v.fields
    assert not any("mutation" in r for r in v.fail_reasons)


# --------------------------------------------------------------------------- #
# P1-7 #7 — reproducibility ignores ONLY timestamp/commit/python_version
# --------------------------------------------------------------------------- #
def test_reproducibility_ignores_only_timestamp_commit_python_version():
    assert set(verify.NONDETERMINISTIC_FIELDS) == {"timestamp_utc", "commit", "python_version"}
    base = {"verdict": "PASS", "line_coverage": 90.0}
    a = {**base, "timestamp_utc": "t1", "commit": "c1", "python_version": "3.11"}
    b = {**base, "timestamp_utc": "t2", "commit": "c2", "python_version": "3.12"}
    assert verify.diff_reproducibility(a, b) == []
    # Any other differing field IS surfaced.
    c = {**a, "line_coverage": 91.0}
    assert verify.diff_reproducibility(a, c) == ["line_coverage"]


# --------------------------------------------------------------------------- #
# P1-5 — explicit bootstrap/enforce verdict assertion
# --------------------------------------------------------------------------- #
def test_verdict_assert_bootstrap_allows_fail_but_not_placeholder(tmp_path):
    verdict_path, manifest = _lay_down_verdict(tmp_path, _sound_verdict_fields(verdict="FAIL"))
    # A sound FAIL passes bootstrap.
    assert_mod.assert_verdict(
        verdict_path, mode="bootstrap", manifest_path=manifest, schema_path=None, root=tmp_path
    )


def test_verdict_assert_bootstrap_rejects_placeholder_sbom(tmp_path):
    fields = _sound_verdict_fields(verdict="FAIL")
    fields["sbom_present"] = False
    verdict_path, manifest = _lay_down_verdict(tmp_path, fields)
    with pytest.raises(assert_mod.AssertError, match="SBOM"):
        assert_mod.assert_verdict(
            verdict_path, mode="bootstrap", manifest_path=manifest, schema_path=None, root=tmp_path
        )


def test_verdict_assert_bootstrap_rejects_absent_mutation(tmp_path):
    fields = _sound_verdict_fields(verdict="FAIL")
    del fields["mutation_bootstrap_report_only"]  # neither real nor bootstrap
    verdict_path, manifest = _lay_down_verdict(tmp_path, fields)
    with pytest.raises(assert_mod.AssertError, match="mutation"):
        assert_mod.assert_verdict(
            verdict_path, mode="bootstrap", manifest_path=manifest, schema_path=None, root=tmp_path
        )


def test_verdict_assert_bootstrap_rejects_tampered_verdict(tmp_path):
    verdict_path, manifest = _lay_down_verdict(tmp_path, _sound_verdict_fields(verdict="FAIL"))
    verdict_path.write_text(verdict_path.read_text() + " ")  # tamper post-hash
    with pytest.raises(assert_mod.AssertError, match="unsound"):
        assert_mod.assert_verdict(
            verdict_path, mode="bootstrap", manifest_path=manifest, schema_path=None, root=tmp_path
        )


def test_verdict_assert_enforce_rejects_fail(tmp_path):
    verdict_path, manifest = _lay_down_verdict(tmp_path, _sound_verdict_fields(verdict="FAIL"))
    with pytest.raises(assert_mod.AssertError, match="expected PASS|real run"):
        assert_mod.assert_verdict(
            verdict_path, mode="enforce", manifest_path=manifest, schema_path=None, root=tmp_path
        )


def test_verdict_assert_enforce_rejects_bootstrap_mutation(tmp_path):
    # Even a PASS verdict cannot enforce on bootstrap (non-real) mutation evidence.
    fields = _sound_verdict_fields(verdict="PASS")
    verdict_path, manifest = _lay_down_verdict(tmp_path, fields)
    with pytest.raises(assert_mod.AssertError, match="real run"):
        assert_mod.assert_verdict(
            verdict_path, mode="enforce", manifest_path=manifest, schema_path=None, root=tmp_path
        )


def test_verdict_assert_enforce_accepts_real_pass(tmp_path):
    fields = _sound_verdict_fields(verdict="PASS")
    del fields["mutation_bootstrap_report_only"]
    fields["mutation_score"] = 90.0
    fields["mutation_score_raw"] = [90, 100]
    fields["mutation_tool"] = "mutmut"
    verdict_path, manifest = _lay_down_verdict(tmp_path, fields)
    assert_mod.assert_verdict(
        verdict_path, mode="enforce", manifest_path=manifest, schema_path=None, root=tmp_path
    )
