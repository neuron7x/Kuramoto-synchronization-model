from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from application.secrets.vault import SecretVaultError
from scripts.secret_management import SecretManagementSuite


@pytest.fixture()
def management_suite(tmp_path: Path) -> SecretManagementSuite:
    storage_path = tmp_path / "vault.json"
    master_key_path = tmp_path / "master.key"
    audit_log_path = tmp_path / "audit.log"
    policy_path = tmp_path / "policy.json"
    return SecretManagementSuite(
        storage_path=storage_path,
        master_key_path=master_key_path,
        audit_log_path=audit_log_path,
        policy_path=policy_path,
        audit_secret="unit-audit-secret",
        actor="secops",
        ip_address="10.0.0.1",
    )


def test_management_suite_end_to_end(management_suite: SecretManagementSuite, tmp_path: Path) -> None:
    suite = management_suite
    metadata = suite.store_secret(
        "services/api",
        "initial-value-1234567890",
        environment="staging",
        rotation_interval=timedelta(days=30),
        labels={"owner": "payments", "runtime_consumer": "gateway"},
    )
    assert metadata.labels["environment"] == "staging"

    secondary = suite.store_secret(
        "services/ops",
        "secondary-value-0987654321",
        environment="production",
        labels={"owner": "sre"},
    )
    assert secondary.labels["owner"] == "sre"

    policy = suite.apply_least_privilege_policy()["policy"]
    assert "payments" in policy and "services/api" in policy["payments"]["read"]

    rotated = suite.rotate_secret("services/api", length=48, reason="unit-test")
    assert rotated.version == metadata.version + 1

    assert suite.enforce_rotation_policies() == []

    audit_events = suite.audit_events(limit=10)
    assert audit_events, "Expected audit events after provisioning"

    filtered = suite.audit_events(secret="services/api")
    assert all(
        entry["record"]["details"]["secret"]["name"] == "services/api" for entry in filtered
    )

    history = suite.export_history()
    assert {entry["name"] for entry in history} >= {"services/api", "services/ops"}

    runtime_file = tmp_path / "runtime.env"
    inject_result = suite.inject_runtime(
        {"API_TOKEN": "services/api"},
        destination=runtime_file,
        format="env",
    )
    assert runtime_file.exists()
    assert "API_TOKEN=" in runtime_file.read_text(encoding="utf-8")
    assert "API_TOKEN" in inject_result["variables"]

    leak_report = suite.scan_repository(tmp_path)
    assert leak_report["total_findings"] == 0

    env_report = suite.validate_environment("staging")
    assert any(item["name"] == "services/ops" for item in env_report["mismatches"])

    ci_report = suite.run_ci_checks(
        tmp_path,
        rotation_grace=timedelta(days=1),
        environment="staging",
    )
    assert ci_report["status"] == "action_required"
    assert ci_report["environment"]["mismatches"], "Expected environment mismatch to surface"

    breakglass_path = tmp_path / "breakglass.txt"
    emergency = suite.issue_emergency_secret(
        "breakglass/root",
        output_path=breakglass_path,
        labels={"owner": "sre"},
    )
    assert breakglass_path.exists()
    assert breakglass_path.read_text(encoding="utf-8").strip()
    assert emergency["metadata"]["labels"]["breakglass"] == "true"

    revoke_metadata = suite.revoke_secret("services/ops", reason="decommissioned")
    assert revoke_metadata["labels"]["status"] == "revoked"

    with pytest.raises(SecretVaultError):
        suite.vault.access_secret(
            "services/ops", actor="secops", ip_address="10.0.0.9"
        )

    failure_results = suite.run_failure_tests()
    assert failure_results["results"], "Failure tests should return individual checks"

    recovery = suite.verify_recovery()
    assert recovery["secret_count"] >= 2
    assert recovery["audit_log_verified"]

