from __future__ import annotations

import json

import pytest

from application.runtime.control_gates import Decision, GateDecision, GatePipelineResult
from tests.helpers.control_platform import build_gate_result


def test_allow_decision_contract() -> None:
    gate = GateDecision(decision=Decision.ALLOW, position_multiplier=0.75, reasons=[])
    assert gate.position_multiplier >= 0
    json.dumps(gate.meta)


def test_throttle_and_deny_contract() -> None:
    throttle = GateDecision(
        decision=Decision.THROTTLE,
        position_multiplier=0.5,
        throttle_ms=1200,
        reasons=["RISK_BUDGET"],
    )
    assert throttle.throttle_ms >= 0
    assert throttle.reasons

    deny = GateDecision(
        decision=Decision.DENY, position_multiplier=1.0, reasons=["CIRCUIT_BREAKER"]
    )
    assert deny.position_multiplier == 0.0
    assert deny.reasons


def test_decision_meta_json_serializable() -> None:
    result: GatePipelineResult = build_gate_result(signals={"risk_score": 1.1})
    payload = {
        "decision": result.gate.decision.value,
        "reasons": result.gate.reasons,
        "meta": result.gate.meta,
    }
    assert json.loads(json.dumps(payload))["decision"] == result.gate.decision.value


def test_throttle_requires_reasons() -> None:
    with pytest.raises(ValueError):
        GateDecision(decision=Decision.THROTTLE, position_multiplier=0.2, reasons=[])
