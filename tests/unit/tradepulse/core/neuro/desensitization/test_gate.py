from __future__ import annotations

from tradepulse.core.neuro.desensitization import (
    DesensitizationGate,
    integration,
)


def test_desensitization_gate_step_returns_expected_shape() -> None:
    gate = DesensitizationGate()
    shaped, size_gate, temp, state = gate.step(
        0.01,
        features=[0.1, 0.2],
        drawdown=0.02,
        vol=0.03,
        hpa_tone=0.1,
        base_temperature=0.9,
    )
    assert isinstance(state, dict)
    assert -10.0 < shaped < 10.0
    assert 0.0 <= size_gate <= 1.0
    assert temp > 0.0


def test_run_gate_step_wraps_output() -> None:
    gate = DesensitizationGate()
    result = integration.run_gate_step(
        gate,
        reward=0.02,
        features=[0.05],
        drawdown=0.01,
        vol=0.02,
        hpa_tone=0.0,
        base_temperature=1.0,
        size_hint=0.5,
    )
    assert result.size <= 0.5
    assert "gate" in result.state["combined"]
