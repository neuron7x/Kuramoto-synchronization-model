"""Heuristic gate decision system for TradePulse.

This module provides a strict, table-driven decision-gating system using
heuristic signals and finite state machines. Unlike the neuroadaptive system,
this implementation uses immutable configuration and raises exceptions on
validation failures.

Key Components:
    - HeuristicDecisionGate: Main decision engine with strict validation
    - HeuristicGateFsm: Table-driven finite state machine
    - HeuristicSignals: Heuristic signal container
    - HeuristicGateConfig: Immutable configuration with calibration support
    - InvalidSignalsError: Exception for validation failures

Example:
    >>> from core.heuristic_gate import (
    ...     HeuristicDecisionGate,
    ...     HeuristicSignals,
    ...     DecisionRequest,
    ...     RiskLevel,
    ... )
    >>>
    >>> # Initialize gate
    >>> gate = HeuristicDecisionGate()
    >>>
    >>> # Create decision request
    >>> signals = HeuristicSignals(
    ...     reward_error=0.5,
    ...     inhibition_strength=0.2,
    ...     risk_score=0.3,
    ...     energy_efficiency=0.8,
    ...     prior_confidence=0.7,
    ... )
    >>> request = DecisionRequest(
    ...     raw_proposal={"action": "buy", "symbol": "BTC"},
    ...     signals=signals,
    ...     risk_level=RiskLevel.MEDIUM,
    ... )
    >>>
    >>> # Make decision
    >>> result = gate.decide(request)
"""

from __future__ import annotations

from .config import HeuristicGateConfig
from .engine import GateMetrics, HeuristicDecisionGate
from .exceptions import InvalidSignalsError
from .fsm import GateTransition, HeuristicGateFsm
from .telemetry import gate_event_payload
from .types import (
    ControlSignal,
    DecisionRequest,
    DecisionResult,
    GateState,
    HeuristicSignals,
    RiskLevel,
)

__all__ = [
    "InvalidSignalsError",
    "GateState",
    "ControlSignal",
    "RiskLevel",
    "HeuristicSignals",
    "DecisionRequest",
    "DecisionResult",
    "HeuristicGateConfig",
    "GateTransition",
    "HeuristicGateFsm",
    "HeuristicDecisionGate",
    "GateMetrics",
    "gate_event_payload",
]
