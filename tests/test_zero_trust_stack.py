from __future__ import annotations

from agent.deployment_gate import DeploymentGate
from agent.self_audit import SelfAuditingModule
from research.formal.truth_oracle import TruthOracle


def test_self_audit_certificate_shape() -> None:
    cert = SelfAuditingModule().compliance_certificate
    assert "determinism_verified" in cert
    assert "invariants_checked" in cert


def test_deployment_gate_boolean() -> None:
    gate = DeploymentGate()
    assert isinstance(gate.can_deploy(), bool)


def test_truth_oracle_certificate_counts() -> None:
    cert = TruthOracle().prove_correctness()
    assert cert.theorems_proved >= cert.theorems_verified
    assert cert.theorems_proved > 0
