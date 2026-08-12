# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from tacl.behavioral_contract import (
    BehavioralContract,
    BehavioralContractViolation,
    ContractBreach,
)
from tacl.energy_model import (
    EnergyMetrics,
    EnergyValidationError,
    EnergyValidationResult,
    EnergyValidator,
)


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
    contract = BehavioralContract(
        rest_potential=0.9, action_potential=1.2, monotonic_tolerance=1e-4
    )

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
    validator = EnergyValidator(max_free_energy=1.6)
    contract = BehavioralContract(action_potential=1.2, rest_potential=0.8)
    metrics_sequence = [
        EnergyMetrics(
            latency_p95=85.0 * 0.5,
            latency_p99=120.0 * 0.5,
            coherency_drift=0.08 * 0.5,
            cpu_burn=0.75 * 0.5,
            mem_cost=6.5 * 0.5,
            queue_depth=32.0 * 0.5,
            packet_loss=0.005 * 0.5,
        ),
        EnergyMetrics(
            latency_p95=85.0 * 0.7,
            latency_p99=120.0 * 0.7,
            coherency_drift=0.08 * 0.7,
            cpu_burn=0.75 * 0.7,
            mem_cost=6.5 * 0.7,
            queue_depth=32.0 * 0.7,
            packet_loss=0.005 * 0.7,
        ),
    ]

    with pytest.raises(BehavioralContractViolation) as exc:
        validator.enforce_contract(metrics_sequence, contract)

    assert any(
        isinstance(breach, ContractBreach) and breach.kind == "action_potential"
        for breach in exc.value.report.breaches
    )


def test_validator_bridge_preserves_free_energy_bound() -> None:
    validator = EnergyValidator(max_free_energy=1.1)
    contract = BehavioralContract(action_potential=1.3, rest_potential=0.8)
    metrics_sequence = [
        EnergyMetrics(
            latency_p95=85.0,
            latency_p99=120.0,
            coherency_drift=0.08,
            cpu_burn=0.75,
            mem_cost=6.5,
            queue_depth=32.0,
            packet_loss=0.005,
        )
    ]

    with pytest.raises(EnergyValidationError):
        validator.enforce_contract(metrics_sequence, contract)
