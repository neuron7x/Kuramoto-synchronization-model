import json
import logging

from application.runtime.control_gates import Decision, GateDecision
from application.runtime.decision_telemetry import (
    CONTROL_GATE_DECISIONS_TOTAL,
    CONTROL_GATE_REASON_TOTAL,
    build_decision_event,
    emit_decision_event,
    fingerprint_config,
    to_json_line,
)


def test_decision_event_serializable_and_proxies() -> None:
    gate = GateDecision(
        decision=Decision.THROTTLE,
        position_multiplier=0.5,
        throttle_ms=120,
        reasons=["RISK_HIGH"],
        meta={"proxy_flags": ["stress_proxy"]},
    )
    telemetry = {
        "serotonin": {"action_gate": "ALLOW", "reason_codes": [], "metrics": {}},
        "thermo": {"controller_state": "OK"},
        "signals": {"risk_score": 2.0, "drawdown": -0.01},
    }
    event = build_decision_event(
        gate=gate,
        telemetry=telemetry,
        effective_config={"alpha": 1, "beta": 2},
        signals=telemetry["signals"],
        trace_id="abc123",
    )
    json_line = to_json_line(event)
    parsed = json.loads(json_line)
    assert parsed["decision"] == "THROTTLE"
    assert parsed["reasons"] == ["RISK_HIGH"]
    assert parsed["proxies"]["proxy_risk"] is True
    assert isinstance(parsed["ts_unix_ms"], int)


def test_config_fingerprint_is_stable() -> None:
    lhs = {"x": 1, "nested": {"y": 2}}
    rhs = {"nested": {"y": 2}, "x": 1}
    assert fingerprint_config(lhs) == fingerprint_config(rhs)


def test_metrics_reason_counters_increment() -> None:
    if CONTROL_GATE_DECISIONS_TOTAL is None or CONTROL_GATE_REASON_TOTAL is None:
        return

    before_decision = CONTROL_GATE_DECISIONS_TOTAL.labels(decision="DENY")._value.get()
    before_reason = CONTROL_GATE_REASON_TOTAL.labels(reason="TEST_REASON")._value.get()

    gate = GateDecision(
        decision=Decision.DENY,
        position_multiplier=0.0,
        throttle_ms=0,
        reasons=["TEST_REASON"],
    )
    telemetry = {"signals": {}}
    event = build_decision_event(
        gate=gate,
        telemetry=telemetry,
        effective_config={"x": 1},
        signals=telemetry["signals"],
        trace_id=None,
    )

    emit_decision_event(event, logger=logging.getLogger("tradepulse.test.telemetry"))

    after_decision = CONTROL_GATE_DECISIONS_TOTAL.labels(decision="DENY")._value.get()
    after_reason = CONTROL_GATE_REASON_TOTAL.labels(reason="TEST_REASON")._value.get()
    assert after_decision == before_decision + 1
    assert after_reason == before_reason + 1
