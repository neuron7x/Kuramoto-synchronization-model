from __future__ import annotations

import pytest

from tacl.behavioral_contract import (
    BehavioralContract,
    BehavioralContractViolation,
    ContractBreach,
)
from tacl.energy_model import EnergyMetrics, EnergyValidationResult, EnergyValidator


def _result(free_energy: float) -> EnergyValidationResult:
    return EnergyValidationResult(
        passed=free_energy <= 1.35,
        free_energy=free_energy,
        internal_energy=free_energy + 0.1,
        entropy=0.2,
        penalties={},
        reason=None,
    )


def test_contract_passes_monotonic_descent() -> None:
    contract = BehavioralContract(rest_potential=0.9, action_potential=1.4)
    report = contract.enforce([_result(1.32), _result(1.25), _result(1.18)])

    assert report.compliant is True
    assert report.breaches == ()


def test_contract_blocks_action_potential_without_approval() -> None:
    contract = BehavioralContract(rest_potential=0.9, action_potential=1.2, monotonic_tolerance=1e-4)

    with pytest.raises(BehavioralContractViolation) as exc:
        contract.enforce([_result(1.18), _result(1.26), _result(1.19)])

    assert exc.value.report.breaches[0].kind == "action_potential"


def test_contract_permits_dual_approval_override() -> None:
    contract = BehavioralContract(required_approvals=frozenset({"operations", "safety"}))
    report = contract.enforce(
        [_result(1.3), _result(1.37)],
        approvals={"operations", "safety", "observer"},
    )

    assert report.overrides_applied is True
    assert report.compliant is False
    kinds = {breach.kind for breach in report.breaches}
    assert "action_potential" in kinds
    assert "monotonicity" in kinds


def test_validator_bridge_enforces_contract() -> None:
    validator = EnergyValidator(max_free_energy=1.2)
    contract = BehavioralContract(action_potential=1.2, rest_potential=0.8)
    metrics_sequence = [
        EnergyMetrics(
            latency_p95=64.0,
            latency_p99=92.0,
            coherency_drift=0.031,
            cpu_burn=0.58,
            mem_cost=4.2,
            queue_depth=18.0,
            packet_loss=0.001,
        ),
        EnergyMetrics(
            latency_p95=128.0,
            latency_p99=164.0,
            coherency_drift=0.25,
            cpu_burn=0.9,
            mem_cost=9.0,
            queue_depth=48.0,
            packet_loss=0.02,
        ),
    ]

    with pytest.raises(BehavioralContractViolation) as exc:
        validator.enforce_contract(metrics_sequence, contract)

    assert any(isinstance(breach, ContractBreach) and breach.kind == "action_potential" for breach in exc.value.report.breaches)
