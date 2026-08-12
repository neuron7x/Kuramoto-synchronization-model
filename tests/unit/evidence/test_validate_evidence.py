"""Tests for the evidence-weight calibration matrix and its validator.

Three contracts:

1. EVIDENCE_MATRIX.yaml is internally consistent.
2. Per-category rules block the F01/F03-class conflations as regression
   cases (range != install, lock != reachable, scanner != reachability,
   green CI != security, MANUAL_INSPECTION != reachability).
3. The cross-claim validator produces the right refusal for each
   regression case fixture in the matrix.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = REPO_ROOT / ".claude" / "evidence" / "EVIDENCE_MATRIX.yaml"
VALIDATOR_PATH = REPO_ROOT / ".claude" / "evidence" / "validate_evidence.py"


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_evidence", VALIDATOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_evidence"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validator() -> ModuleType:
    return _load_validator()


@pytest.fixture(scope="module")
def matrix(validator: ModuleType) -> dict[str, Any]:
    loaded: dict[str, Any] = validator.load_matrix(MATRIX_PATH)
    return loaded


# ---------------------------------------------------------------------------
# Contract 1 — matrix is internally consistent
# ---------------------------------------------------------------------------


def test_matrix_loads(matrix: dict[str, Any]) -> None:
    assert matrix.get("schema_version") == 1
    assert matrix.get("categories"), "matrix has no categories"
    assert matrix.get("prohibited_overclaims"), "matrix has no overclaims"


def test_matrix_self_validates(validator: ModuleType, matrix: dict[str, Any]) -> None:
    errors = validator.validate_matrix(matrix)
    assert not errors, "matrix self-validation failed:\n" + "\n".join(str(e) for e in errors)


def test_all_13_evidence_categories_present(matrix: dict[str, Any]) -> None:
    expected = {
        "FILE_DECLARATION",
        "LOCKFILE_PIN",
        "RESOLVER_OUTPUT",
        "SCANNER_OUTPUT",
        "RUNTIME_IMPORT_SMOKE",
        "UNIT_TEST",
        "INTEGRATION_TEST",
        "MUTATION_TEST",
        "CI_STATUS",
        "MANUAL_INSPECTION",
        "EXTERNAL_ADVISORY",
        "BENCHMARK",
        "DATASET_RESULT",
    }
    assert set(matrix["categories"].keys()) == expected


def test_overclaim_refusal_messages_are_non_empty(matrix: dict[str, Any]) -> None:
    for name, body in matrix["prohibited_overclaims"].items():
        msg = (body.get("refusal_message") or "").strip()
        assert msg, f"overclaim {name} has empty refusal_message"


# ---------------------------------------------------------------------------
# Contract 2 — F01/F03 regression cases (encoded in YAML, executed in tests)
# ---------------------------------------------------------------------------


def test_regression_cases_present(matrix: dict[str, Any]) -> None:
    cases = matrix.get("regression_cases") or []
    names = {c["name"] for c in cases}
    required = {
        "F01_RANGE_CLAIMS_ACTIVE_INSTALL",
        "F03_LOCK_CLAIMS_EXPLOIT_PATH",
        "SCANNER_CLAIMS_REACHABILITY",
        "GREEN_CI_CLAIMS_SECURITY",
        "MANUAL_INSPECTION_CLAIMS_REACHABILITY",
    }
    missing = required - names
    assert not missing, f"missing required regression cases: {sorted(missing)}"


def test_each_regression_case_actually_refuses(
    validator: ModuleType, matrix: dict[str, Any]
) -> None:
    """Every regression_cases entry must be refused by the validator."""
    cases = matrix.get("regression_cases") or []
    failed_to_refuse: list[str] = []
    for case in cases:
        cname = case["name"]
        shape = case["claim_shape"]
        expected = case["expected_refusal"]
        errors = validator.check_claim_against_matrix(
            matrix,
            claim_class=shape["class"],
            tier=shape["tier"],
            evidence_types=shape["evidence_types"],
            asserts=[shape["asserts"]],
        )
        # The expected refusal must appear in the errors `where` field.
        if not any(e.where == expected for e in errors):
            failed_to_refuse.append(
                f"{cname}: expected refusal {expected!r}, got {[e.where for e in errors]}"
            )
    assert not failed_to_refuse, "\n".join(failed_to_refuse)


# ---------------------------------------------------------------------------
# Contract 3 — direct injection: at least 4 overclaim refusals
# ---------------------------------------------------------------------------


def test_inject_f01_active_install_via_file_declaration(
    validator: ModuleType, matrix: dict[str, Any]
) -> None:
    """F01: a FILE_DECLARATION + ACTIVE_VULNERABLE_INSTALL claim is refused."""
    errors = validator.check_claim_against_matrix(
        matrix,
        claim_class="SECURITY",
        tier="FACT",
        evidence_types=["FILE_DECLARATION"],
        asserts=["ACTIVE_VULNERABLE_INSTALL"],
    )
    assert any(
        e.where == "ACTIVE_VULNERABLE_INSTALL" and "OVERCLAIM" in e.rule for e in errors
    ), errors


def test_inject_f03_exploit_path_via_lockfile(
    validator: ModuleType, matrix: dict[str, Any]
) -> None:
    """F03: LOCKFILE_PIN + EXPLOIT_PATH_CONFIRMED claim is refused."""
    errors = validator.check_claim_against_matrix(
        matrix,
        claim_class="SECURITY",
        tier="FACT",
        evidence_types=["LOCKFILE_PIN", "EXTERNAL_ADVISORY"],
        asserts=["EXPLOIT_PATH_CONFIRMED"],
    )
    assert any(
        e.where == "EXPLOIT_PATH_CONFIRMED" and "OVERCLAIM" in e.rule for e in errors
    ), errors


def test_inject_scanner_reachability_refused(validator: ModuleType, matrix: dict[str, Any]) -> None:
    """SCANNER_OUTPUT alone cannot back RUNTIME_REACHABILITY."""
    errors = validator.check_claim_against_matrix(
        matrix,
        claim_class="SECURITY",
        tier="FACT",
        evidence_types=["SCANNER_OUTPUT"],
        asserts=["RUNTIME_REACHABILITY"],
    )
    assert any(e.where == "RUNTIME_REACHABILITY" and "OVERCLAIM" in e.rule for e in errors), errors


def test_inject_green_ci_security_refused(validator: ModuleType, matrix: dict[str, Any]) -> None:
    """CI_STATUS alone cannot back SECURITY_VERIFICATION."""
    errors = validator.check_claim_against_matrix(
        matrix,
        claim_class="SECURITY",
        tier="FACT",
        evidence_types=["CI_STATUS"],
        asserts=["SECURITY_VERIFICATION"],
    )
    assert any(e.where == "SECURITY_VERIFICATION" and "OVERCLAIM" in e.rule for e in errors), errors


def test_inject_manual_inspection_reachability_refused(
    validator: ModuleType, matrix: dict[str, Any]
) -> None:
    """MANUAL_INSPECTION alone cannot prove RUNTIME_REACHABILITY."""
    errors = validator.check_claim_against_matrix(
        matrix,
        claim_class="SECURITY",
        tier="FACT",
        evidence_types=["MANUAL_INSPECTION"],
        asserts=["RUNTIME_REACHABILITY"],
    )
    assert any(e.where == "RUNTIME_REACHABILITY" and "OVERCLAIM" in e.rule for e in errors), errors


def test_bug_free_code_is_never_supportable(validator: ModuleType, matrix: dict[str, Any]) -> None:
    """An overclaim with requires_any_of=[] (BUG_FREE_CODE) is always refused."""
    errors = validator.check_claim_against_matrix(
        matrix,
        claim_class="GOVERNANCE",
        tier="FACT",
        evidence_types=["MUTATION_TEST", "INTEGRATION_TEST"],
        asserts=["BUG_FREE_CODE"],
    )
    assert any(
        e.where == "BUG_FREE_CODE" and e.rule == "OVERCLAIM_FORBIDDEN" for e in errors
    ), errors


# ---------------------------------------------------------------------------
# Contract 4 — supported claims pass cleanly
# ---------------------------------------------------------------------------


def test_legitimate_F01_range_drift_passes(validator: ModuleType, matrix: dict[str, Any]) -> None:
    """A correctly framed F01 claim — manifest hygiene, not active install."""
    errors = validator.check_claim_against_matrix(
        matrix,
        claim_class="SECURITY",
        tier="FACT",
        evidence_types=["FILE_DECLARATION", "RESOLVER_OUTPUT"],
        asserts=[],  # claim does NOT assert ACTIVE_VULNERABLE_INSTALL
    )
    assert not errors, errors


def test_legitimate_F03_version_risk_passes(validator: ModuleType, matrix: dict[str, Any]) -> None:
    """A correctly framed F03 claim — version risk closed, not reachability."""
    errors = validator.check_claim_against_matrix(
        matrix,
        claim_class="SECURITY",
        tier="FACT",
        evidence_types=["LOCKFILE_PIN", "SCANNER_OUTPUT", "EXTERNAL_ADVISORY"],
        asserts=[],  # does NOT assert EXPLOIT_PATH_CONFIRMED
    )
    assert not errors, errors


def test_integration_backed_reachability_claim_passes(
    validator: ModuleType, matrix: dict[str, Any]
) -> None:
    """RUNTIME_REACHABILITY backed by INTEGRATION_TEST is allowed."""
    errors = validator.check_claim_against_matrix(
        matrix,
        claim_class="SECURITY",
        tier="FACT",
        evidence_types=["INTEGRATION_TEST"],
        asserts=["RUNTIME_REACHABILITY"],
    )
    assert not errors, errors


# ---------------------------------------------------------------------------
# Contract 5 — companion rules
# ---------------------------------------------------------------------------


def test_file_declaration_alone_cannot_be_FACT(
    validator: ModuleType, matrix: dict[str, Any]
) -> None:
    """FILE_DECLARATION requires a companion (LOCKFILE/RESOLVER/SCANNER)."""
    errors = validator.check_claim_against_matrix(
        matrix,
        claim_class="SECURITY",
        tier="FACT",
        evidence_types=["FILE_DECLARATION"],
        asserts=[],
    )
    assert any(e.rule == "FACT_COMPANION_REQUIRED" for e in errors), errors


def test_runtime_smoke_alone_cannot_be_FACT(validator: ModuleType, matrix: dict[str, Any]) -> None:
    """RUNTIME_IMPORT_SMOKE alone proves wiring, not behaviour."""
    errors = validator.check_claim_against_matrix(
        matrix,
        claim_class="RELIABILITY",
        tier="FACT",
        evidence_types=["RUNTIME_IMPORT_SMOKE"],
        asserts=[],
    )
    assert any(e.rule == "FACT_COMPANION_REQUIRED" for e in errors), errors


def test_ci_status_alone_cannot_be_FACT(validator: ModuleType, matrix: dict[str, Any]) -> None:
    """CI_STATUS alone is too weak for FACT — needs an integration/mutation
    or scanner companion."""
    errors = validator.check_claim_against_matrix(
        matrix,
        claim_class="GOVERNANCE",
        tier="FACT",
        evidence_types=["CI_STATUS"],
        asserts=[],
    )
    assert any(e.rule in ("TIER_NOT_ALLOWED", "FACT_COMPANION_REQUIRED") for e in errors), errors


def test_validator_main_returns_zero_on_clean_matrix(
    validator: ModuleType,
) -> None:
    rc = validator.main(["--matrix", str(MATRIX_PATH)])
    assert rc == 0
