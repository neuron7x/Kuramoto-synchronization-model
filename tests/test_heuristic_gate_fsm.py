"""Tests for heuristic gate FSM."""

from __future__ import annotations

from core.heuristic_gate.config import HeuristicGateConfig
from core.heuristic_gate.fsm import HeuristicGateFsm
from core.heuristic_gate.types import ControlSignal, GateState


def test_reset_from_any_state() -> None:
    """Test that RESET signal returns to REFLEX from any state."""
    cfg = HeuristicGateConfig.default()
    fsm = HeuristicGateFsm(cfg)
    for state in GateState:
        fsm._state = state  # internal test access
        fsm.apply(ControlSignal.RESET, "test")
        assert fsm.state is GateState.REFLEX
