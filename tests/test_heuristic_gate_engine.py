"""Tests for heuristic gate engine."""

from __future__ import annotations

from core.heuristic_gate.engine import HeuristicDecisionGate
from core.heuristic_gate.exceptions import InvalidSignalsError
from core.heuristic_gate.types import (
    DecisionRequest,
    GateState,
    HeuristicSignals,
    RiskLevel,
)


def test_out_of_range_raises() -> None:
    """Test that out-of-range signals raise InvalidSignalsError."""
    gate = HeuristicDecisionGate()
    req = DecisionRequest(
        raw_proposal="test",
        signals=HeuristicSignals(reward_error=999.0),
        risk_level=RiskLevel.LOW,
    )
    raised = False
    try:
        gate.decide(req)
    except InvalidSignalsError as exc:
        raised = True
        assert "reward_error out of range" in exc.issues[0]
    assert raised


def test_high_confidence_low_risk_allows() -> None:
    """Test that high confidence with low risk allows the decision."""
    gate = HeuristicDecisionGate()
    req = DecisionRequest(
        raw_proposal="test",
        signals=HeuristicSignals(
            reward_error=1.0,
            inhibition_strength=0.0,
            risk_score=0.0,
            energy_efficiency=1.0,
        ),
        risk_level=RiskLevel.LOW,
    )
    result = gate.decide(req)
    assert result.allowed is True
    assert result.gate_state is GateState.RELEASED
    assert 0.0 <= result.blended_confidence <= 1.0
