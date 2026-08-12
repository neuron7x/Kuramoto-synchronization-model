from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.claims.validate_claims_have_evidence import validate


@pytest.fixture
def audit_root(tmp_path: Path) -> Path:
    root = tmp_path / "reports" / "test_audit"
    root.mkdir(parents=True)
    return root


def _write_evidence(path: Path, claims: list[dict]) -> Path:
    payload = {"schema_version": "1.1", "claims": claims}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _base_claim(**kwargs: object) -> dict[str, object]:
    data: dict[str, object] = {
        "claim_id": "C1",
        "claim_text": "sample claim",
        "domain": "testing",
        "claim_status": "proven",
        "command": "pytest -q",
        "artifact_path": "",
        "verdict": "accepted",
        "release_decision": "allow",
        "last_verified_sha": "abc",
        "timestamp_utc": "2026-05-22T00:00:00Z",
    }
    data.update(kwargs)
    return data


def test_valid_proven_claim_with_real_artifact_passes(tmp_path: Path, audit_root: Path) -> None:
    artifact = tmp_path / "proof.txt"
    artifact.write_text("ok", encoding="utf-8")
    evidence = _write_evidence(
        tmp_path / "evidence.json", [_base_claim(artifact_path=str(artifact))]
    )
    assert validate(evidence, audit_root=audit_root) == []


def test_proven_claim_without_artifact_path_fails(tmp_path: Path, audit_root: Path) -> None:
    evidence = _write_evidence(tmp_path / "evidence.json", [_base_claim(artifact_path="")])
    assert validate(evidence, audit_root=audit_root)


def test_artifact_manifest_valid_passes(tmp_path: Path, audit_root: Path) -> None:
    baseline = audit_root / "baseline_run_test_valid"
    baseline.mkdir(parents=True)
    artifact = baseline / "a.txt"
    artifact.write_text("x", encoding="utf-8")
    import hashlib

    h = hashlib.sha256(artifact.read_bytes()).hexdigest()
    (baseline / "artifact_manifest.sha256").write_text(f"{h} a.txt\n", encoding="utf-8")
    evidence = _write_evidence(
        tmp_path / "evidence.json", [_base_claim(artifact_path=str(artifact))]
    )
    assert validate(evidence, audit_root=audit_root, manifest_scope="referenced") == []


def test_manifest_mismatch_fails_for_referenced_baseline(tmp_path: Path, audit_root: Path) -> None:
    baseline = audit_root / "baseline_run_test_mismatch"
    baseline.mkdir(parents=True)
    artifact = baseline / "pytest.log"
    artifact.write_text("ok", encoding="utf-8")
    (baseline / "artifact_manifest.sha256").write_text("deadbeef coverage.xml\n", encoding="utf-8")
    evidence = _write_evidence(
        tmp_path / "evidence.json", [_base_claim(artifact_path=str(artifact))]
    )
    errors = validate(evidence, audit_root=audit_root, manifest_scope="referenced")
    assert any("missing" in error or "mismatch" in error for error in errors)


def test_failed_baseline_only_allowed_for_failure_detection(
    tmp_path: Path, audit_root: Path
) -> None:
    baseline = audit_root / "baseline_run_test_failed"
    baseline.mkdir(parents=True)
    (baseline / "exit_code.txt").write_text("1\n", encoding="utf-8")
    artifact = baseline / "junit.xml"
    artifact.write_text("<testsuite/>", encoding="utf-8")

    evidence = _write_evidence(
        tmp_path / "evidence.json",
        [_base_claim(artifact_path=str(artifact), claim_text="test suite passes")],
    )
    assert validate(evidence, audit_root=audit_root)


def test_manifest_scope_all_reports_unreferenced_manifest_errors(
    tmp_path: Path, audit_root: Path
) -> None:
    artifact = tmp_path / "proof.txt"
    artifact.write_text("ok", encoding="utf-8")
    evidence = _write_evidence(
        tmp_path / "evidence.json", [_base_claim(artifact_path=str(artifact))]
    )

    unreferenced = audit_root / "baseline_run_test_unreferenced"
    unreferenced.mkdir(parents=True)
    (unreferenced / "artifact_manifest.sha256").write_text(
        "deadbeef pytest.log\n", encoding="utf-8"
    )

    errors = validate(evidence, audit_root=audit_root, manifest_scope="all")
    assert any("missing" in error for error in errors)


def test_manifest_scope_none_skips_manifest_validation(tmp_path: Path, audit_root: Path) -> None:
    artifact = tmp_path / "proof.txt"
    artifact.write_text("ok", encoding="utf-8")
    evidence = _write_evidence(
        tmp_path / "evidence.json", [_base_claim(artifact_path=str(artifact))]
    )

    bad = audit_root / "baseline_run_test_none"
    bad.mkdir(parents=True)
    (bad / "artifact_manifest.sha256").write_text("deadbeef missing.log\n", encoding="utf-8")

    assert validate(evidence, audit_root=audit_root, manifest_scope="none") == []


def test_relative_artifact_path_resolves_against_audit_root(
    tmp_path: Path, audit_root: Path
) -> None:
    baseline = audit_root / "baseline_run_test_rel"
    baseline.mkdir(parents=True)
    artifact = baseline / "pytest.log"
    artifact.write_text("ok", encoding="utf-8")

    evidence = _write_evidence(
        tmp_path / "evidence.json", [_base_claim(artifact_path="baseline_run_test_rel/pytest.log")]
    )

    assert validate(evidence, audit_root=audit_root, manifest_scope="referenced") == []


def test_relative_artifact_path_marks_referenced_baseline_for_manifest_validation(
    tmp_path: Path, audit_root: Path
) -> None:
    baseline = audit_root / "baseline_run_test_rel_bad"
    baseline.mkdir(parents=True)
    artifact = baseline / "pytest.log"
    artifact.write_text("ok", encoding="utf-8")
    (baseline / "artifact_manifest.sha256").write_text("deadbeef coverage.xml\n", encoding="utf-8")

    evidence = _write_evidence(
        tmp_path / "evidence.json",
        [_base_claim(artifact_path="baseline_run_test_rel_bad/pytest.log")],
    )

    errors = validate(evidence, audit_root=audit_root, manifest_scope="referenced")
    assert any("missing" in error for error in errors)


def test_default_manifest_scope_validates_all_manifests(tmp_path: Path, audit_root: Path) -> None:
    artifact = tmp_path / "proof.txt"
    artifact.write_text("ok", encoding="utf-8")
    evidence = _write_evidence(
        tmp_path / "evidence.json", [_base_claim(artifact_path=str(artifact))]
    )

    bad = audit_root / "baseline_run_test_global"
    bad.mkdir(parents=True)
    (bad / "artifact_manifest.sha256").write_text("deadbeef missing.log\n", encoding="utf-8")

    errors = validate(evidence, audit_root=audit_root)
    assert any("missing" in error for error in errors)


def test_manifest_scope_referenced_ignores_unreferenced_bad_manifest(
    tmp_path: Path, audit_root: Path
) -> None:
    artifact = tmp_path / "proof.txt"
    artifact.write_text("ok", encoding="utf-8")
    evidence = _write_evidence(
        tmp_path / "evidence.json", [_base_claim(artifact_path=str(artifact))]
    )

    bad = audit_root / "baseline_run_test_unref"
    bad.mkdir(parents=True)
    (bad / "artifact_manifest.sha256").write_text("deadbeef missing.log\n", encoding="utf-8")

    assert validate(evidence, audit_root=audit_root, manifest_scope="referenced") == []


def test_relative_artifact_path_resolves_when_cwd_changes(
    tmp_path: Path, audit_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = audit_root / "baseline_run_test_cwd"
    baseline.mkdir(parents=True)
    artifact = baseline / "pytest.log"
    artifact.write_text("ok", encoding="utf-8")

    evidence = _write_evidence(
        tmp_path / "evidence.json", [_base_claim(artifact_path="baseline_run_test_cwd/pytest.log")]
    )

    other = tmp_path / "othercwd"
    other.mkdir()
    monkeypatch.chdir(other)

    assert validate(evidence, audit_root=audit_root, manifest_scope="referenced") == []


def test_failed_baseline_cannot_be_bypassed_by_claim_text(tmp_path: Path, audit_root: Path) -> None:
    baseline = audit_root / "baseline_run_test_failed_text"
    baseline.mkdir(parents=True)
    (baseline / "exit_code.txt").write_text("1\n", encoding="utf-8")
    artifact = baseline / "pytest.log"
    artifact.write_text("ok", encoding="utf-8")

    evidence = _write_evidence(
        tmp_path / "evidence.json",
        [
            _base_claim(
                artifact_path=str(artifact),
                claim_text="failure budget check",
                release_decision="allow",
            )
        ],
    )

    errors = validate(evidence, audit_root=audit_root, manifest_scope="referenced")
    assert any("failed baseline artifact" in error for error in errors)


def test_failed_baseline_allowed_when_release_decision_explicitly_blocked(
    tmp_path: Path, audit_root: Path
) -> None:
    baseline = audit_root / "baseline_run_test_failed_blocked"
    baseline.mkdir(parents=True)
    (baseline / "exit_code.txt").write_text("1\n", encoding="utf-8")
    artifact = baseline / "pytest.log"
    artifact.write_text("ok", encoding="utf-8")

    evidence = _write_evidence(
        tmp_path / "evidence.json",
        [_base_claim(artifact_path=str(artifact), release_decision="blocked")],
    )

    errors = validate(evidence, audit_root=audit_root, manifest_scope="referenced")
    assert not any("failed baseline artifact" in error for error in errors)


def test_invalid_evidence_json_returns_validation_error(tmp_path: Path, audit_root: Path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{bad json", encoding="utf-8")
    errors = validate(evidence, audit_root=audit_root)
    assert any("Invalid evidence index JSON" in e for e in errors)


def test_non_dict_claim_entry_is_reported(tmp_path: Path, audit_root: Path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({"schema_version": "1.1", "claims": ["bad"]}), encoding="utf-8")
    errors = validate(evidence, audit_root=audit_root, manifest_scope="none")
    assert any("invalid claim entry type" in e for e in errors)
