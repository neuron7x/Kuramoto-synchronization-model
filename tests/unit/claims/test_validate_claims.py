"""Tests for the claim ledger validator.

Two contracts:

1. The shipping ledger (.claude/claims/CLAIMS.yaml) validates clean.
2. Each documented failure mode (FACT without evidence, SECURITY without
   scanner / advisory / lockfile / file-declaration / resolver evidence,
   missing falsifier, missing owner_surface, broken evidence path,
   duplicate claim_id, FACT without test or non_testable_reason) is
   detected by the validator. These are the load-bearing regression
   tests for the calibration layer.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from textwrap import dedent
from types import ModuleType
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = REPO_ROOT / ".claude" / "claims" / "validate_claims.py"
SHIPPING_LEDGER = REPO_ROOT / ".claude" / "claims" / "CLAIMS.yaml"


def _load_validator() -> ModuleType:
    """Import .claude/claims/validate_claims.py without adding it to sys.path."""
    spec = importlib.util.spec_from_file_location("validate_claims", VALIDATOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_claims"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validator() -> ModuleType:
    return _load_validator()


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    """A temporary repository root with the minimal files referenced by claims."""
    (tmp_path / ".claude" / "claims").mkdir(parents=True)
    (tmp_path / "evidence_a.md").write_text("evidence-a", encoding="utf-8")
    (tmp_path / "evidence_b.md").write_text("evidence-b", encoding="utf-8")
    (tmp_path / "test_a.py").write_text("# test", encoding="utf-8")
    (tmp_path / "scanner_a.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _write_ledger(repo: Path, claims: list[dict[str, Any]]) -> Path:
    ledger_path = repo / ".claude" / "claims" / "CLAIMS.yaml"
    ledger_path.write_text(
        yaml.safe_dump({"schema_version": 1, "claims": claims}, sort_keys=False),
        encoding="utf-8",
    )
    return ledger_path


def _good_claim(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "claim_id": "TEST-OK",
        "statement": "test claim",
        "class": "SECURITY",
        "tier": "FACT",
        "evidence_paths": [{"type": "FILE_DECLARATION", "path": "evidence_a.md", "capture": "x"}],
        "test_paths": ["test_a.py"],
        "falsifier": "evidence_a.md is missing",
        "owner_surface": "test/surface",
        "last_verified_command": "true",
        "status": "ACTIVE",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Contract 1 — shipping ledger validates clean
# ---------------------------------------------------------------------------


def test_shipping_ledger_validates_clean(validator: ModuleType) -> None:
    """The repository's CLAIMS.yaml must validate against its own validator."""
    errors = validator.validate_ledger(SHIPPING_LEDGER, REPO_ROOT)
    assert not errors, "shipping ledger has errors:\n" + "\n".join(str(e) for e in errors)


# ---------------------------------------------------------------------------
# Contract 2 — injection cases: each rule must catch a planted failure
# ---------------------------------------------------------------------------


def test_inject_fact_without_evidence_fails(validator: ModuleType, fake_repo: Path) -> None:
    bad = _good_claim(evidence_paths=[])
    ledger = _write_ledger(fake_repo, [bad])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    assert "FACT_NO_EVIDENCE" in rules, errors


def test_inject_fact_without_test_or_reason_fails(validator: ModuleType, fake_repo: Path) -> None:
    bad = _good_claim(test_paths=[])
    ledger = _write_ledger(fake_repo, [bad])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    assert "FACT_NO_TEST" in rules, errors


def test_fact_without_test_passes_with_explicit_reason(
    validator: ModuleType, fake_repo: Path
) -> None:
    """non_testable_reason must release the test_paths requirement."""
    bad = _good_claim(
        test_paths=[],
        non_testable_reason="Reachability follow-up tracked in issue #999",
    )
    ledger = _write_ledger(fake_repo, [bad])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    assert "FACT_NO_TEST" not in rules, errors


def test_inject_no_falsifier_fails(validator: ModuleType, fake_repo: Path) -> None:
    bad = _good_claim(falsifier="")
    ledger = _write_ledger(fake_repo, [bad])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    assert "NO_FALSIFIER" in rules, errors


def test_inject_no_owner_surface_fails(validator: ModuleType, fake_repo: Path) -> None:
    bad = _good_claim(owner_surface="")
    ledger = _write_ledger(fake_repo, [bad])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    assert "NO_OWNER_SURFACE" in rules, errors


def test_inject_broken_evidence_path_fails(validator: ModuleType, fake_repo: Path) -> None:
    bad = _good_claim(
        evidence_paths=[{"type": "FILE_DECLARATION", "path": "does_not_exist.md", "capture": "x"}]
    )
    ledger = _write_ledger(fake_repo, [bad])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    assert "EVIDENCE_PATH_NOT_FOUND" in rules, errors


def test_inject_broken_test_path_fails(validator: ModuleType, fake_repo: Path) -> None:
    bad = _good_claim(test_paths=["does_not_exist.py"])
    ledger = _write_ledger(fake_repo, [bad])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    assert "TEST_PATH_NOT_FOUND" in rules, errors


def test_inject_duplicate_claim_id_fails(validator: ModuleType, fake_repo: Path) -> None:
    a = _good_claim(claim_id="DUP-1")
    b = _good_claim(claim_id="DUP-1")
    ledger = _write_ledger(fake_repo, [a, b])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    assert "DUPLICATE_CLAIM_ID" in rules, errors


def test_inject_security_fact_without_security_evidence_fails(
    validator: ModuleType, fake_repo: Path
) -> None:
    """SECURITY/FACT cannot rest on MANUAL_INSPECTION alone — F03 trap."""
    bad = _good_claim(
        evidence_paths=[{"type": "MANUAL_INSPECTION", "path": "evidence_a.md", "capture": "x"}]
    )
    ledger = _write_ledger(fake_repo, [bad])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    assert "SECURITY_FACT_INSUFFICIENT_EVIDENCE" in rules, errors


def test_inject_scientific_without_falsifier_fails(validator: ModuleType, fake_repo: Path) -> None:
    bad = _good_claim(
        claim_id="SCI-1",
        **{"class": "SCIENTIFIC"},
        falsifier="",
    )
    ledger = _write_ledger(fake_repo, [bad])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    # NO_FALSIFIER fires generally, plus SCIENTIFIC_NO_FALSIFIER specifically.
    assert "SCIENTIFIC_NO_FALSIFIER" in rules or "NO_FALSIFIER" in rules, errors


def test_inject_performance_fact_without_benchmark_fails(
    validator: ModuleType, fake_repo: Path
) -> None:
    bad = _good_claim(
        claim_id="PERF-1",
        **{"class": "PERFORMANCE"},
        evidence_paths=[{"type": "MANUAL_INSPECTION", "path": "evidence_a.md", "capture": "x"}],
    )
    ledger = _write_ledger(fake_repo, [bad])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    assert "PERFORMANCE_FACT_NO_BENCHMARK" in rules, errors


def test_unknown_evidence_type_fails(validator: ModuleType, fake_repo: Path) -> None:
    bad = _good_claim(
        evidence_paths=[{"type": "ASTROLOGICAL_HUNCH", "path": "evidence_a.md", "capture": "x"}]
    )
    ledger = _write_ledger(fake_repo, [bad])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    assert "EVIDENCE_TYPE_UNKNOWN" in rules, errors


def test_rejected_claim_with_no_reason_fails(validator: ModuleType, fake_repo: Path) -> None:
    bad = _good_claim(status="REJECTED")  # no rejection_reason
    ledger = _write_ledger(fake_repo, [bad])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    assert "REJECTED_NO_REASON" in rules, errors


def test_rejected_claim_with_reason_passes(validator: ModuleType, fake_repo: Path) -> None:
    """REJECTED claims are kept for audit; they bypass active gates."""
    bad = _good_claim(
        tier="SPECULATION",
        status="REJECTED",
        rejection_reason="contradicted by 2026-04-26 audit",
        evidence_paths=[],
        test_paths=[],
        falsifier="",
        owner_surface="",
    )
    ledger = _write_ledger(fake_repo, [bad])
    errors = validator.validate_ledger(ledger, fake_repo)
    rules = {e.rule for e in errors}
    # REJECTED bypasses NO_FALSIFIER / NO_OWNER_SURFACE / FACT_NO_*
    assert "NO_FALSIFIER" not in rules
    assert "NO_OWNER_SURFACE" not in rules


def test_yaml_parse_error_returns_clean_diagnostic(validator: ModuleType, fake_repo: Path) -> None:
    ledger = fake_repo / ".claude" / "claims" / "CLAIMS.yaml"
    ledger.write_text(
        dedent("""
            schema_version: 1
            claims:
              - claim_id: BAD
                statement: |
                  unterminated
                : oops
            """),
        encoding="utf-8",
    )
    errors = validator.validate_ledger(ledger, fake_repo)
    assert errors and any(e.rule == "YAML_PARSE_ERROR" for e in errors), errors


def test_unsupported_schema_version_fails(validator: ModuleType, fake_repo: Path) -> None:
    ledger = fake_repo / ".claude" / "claims" / "CLAIMS.yaml"
    ledger.write_text(yaml.safe_dump({"schema_version": 99, "claims": []}), encoding="utf-8")
    errors = validator.validate_ledger(ledger, fake_repo)
    assert any(e.rule == "SCHEMA_VERSION" for e in errors), errors


def test_missing_ledger_file_fails(validator: ModuleType, tmp_path: Path) -> None:
    errors = validator.validate_ledger(tmp_path / "absent.yaml", tmp_path)
    assert any(e.rule == "LEDGER_NOT_FOUND" for e in errors), errors


def test_validator_main_returns_zero_on_clean_ledger(
    validator: ModuleType,
) -> None:
    rc = validator.main(["--ledger", str(SHIPPING_LEDGER), "--repo-root", str(REPO_ROOT)])
    assert rc == 0


def test_validator_main_returns_nonzero_on_dirty_ledger(
    validator: ModuleType, fake_repo: Path
) -> None:
    bad = _good_claim(falsifier="")
    ledger = _write_ledger(fake_repo, [bad])
    rc = validator.main(["--ledger", str(ledger), "--repo-root", str(fake_repo)])
    assert rc == 1
