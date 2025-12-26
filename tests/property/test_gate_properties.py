from __future__ import annotations

import math
import random
from typing import Mapping

from application.runtime.control_gates import Decision
from application.settings import BackendRuntimeSettings
from tests.helpers.control_platform import (
    StubSerotoninController,
    StubThermoController,
    build_gate_result,
)


def _severity(decision: Decision) -> int:
    return {Decision.ALLOW: 0, Decision.THROTTLE: 1, Decision.DENY: 2}[decision]


def _build_signals(rng: random.Random) -> Mapping[str, float]:
    return {
        "risk_score": rng.uniform(0.0, 3.0),
        "volatility": rng.uniform(0.5, 2.5),
        "drawdown": -abs(rng.uniform(0.0, 0.1)),
        "free_energy": rng.uniform(0.0, 1.5),
    }


def test_outputs_bounded_and_finite() -> None:
    rng = random.Random(1234)
    runtime_settings = BackendRuntimeSettings(
        gate_defaults={"min_position_multiplier": 0.0, "max_position_multiplier": 1.0, "default_decision": "ALLOW"}
    )
    for _ in range(20):
        signals = _build_signals(rng)
        result = build_gate_result(
            signals=signals,
            runtime_settings=runtime_settings,
            serotonin=StubSerotoninController(),
            thermo=StubThermoController(),
        )
        gate = result.gate
        assert math.isfinite(gate.position_multiplier)
        assert gate.position_multiplier >= 0
        assert gate.throttle_ms >= 0


def test_safety_monotonicity_with_risk() -> None:
    rng = random.Random(99)
    base_signals = _build_signals(rng)
    higher_risk = dict(base_signals)
    higher_risk["risk_score"] = base_signals["risk_score"] + 1.5

    result_low = build_gate_result(signals=base_signals)
    result_high = build_gate_result(signals=higher_risk)

    assert _severity(result_high.gate.decision) >= _severity(result_low.gate.decision)


def test_safety_monotonicity_with_free_energy() -> None:
    baseline = {"risk_score": 1.0, "volatility": 1.0, "drawdown": -0.02, "free_energy": 0.1}
    elevated = dict(baseline)
    elevated["free_energy"] = 1.0

    result_low = build_gate_result(signals=baseline)
    result_high = build_gate_result(signals=elevated)

    assert _severity(result_high.gate.decision) >= _severity(result_low.gate.decision)


def test_determinism_for_same_inputs() -> None:
    signals = {"risk_score": 0.8, "volatility": 1.0, "drawdown": -0.01, "free_energy": 0.2}
    first = build_gate_result(signals=signals)
    second = build_gate_result(signals=signals)
    assert first.gate.decision == second.gate.decision
    assert first.gate.reasons == second.gate.reasons
    assert first.gate.position_multiplier == second.gate.position_multiplier
