"""Neuroadaptive decision system for TradePulse.

This module provides a sophisticated decision-making system inspired by
neuroscience, using neuromodulator-like signals and finite state machines
to gate trading decisions with risk awareness.

Key Components:
    - NeuroAdaptiveAgent: Main decision engine
    - NeuroGateFsm: Finite state machine for gate control
    - NeuroSignals: Neuromodulator-inspired signal container
    - NeuroAdaptiveConfig: Configuration and validation

Example:
    >>> from core.neuroadaptive import (
    ...     NeuroAdaptiveAgent,
    ...     NeuroSignals,
    ...     DecisionRequest,
    ... )
    >>>
    >>> # Create mock LLM client
    >>> class MockLlm:
    ...     async def complete(self, prompt: str, **kwargs) -> str:
    ...         return "mock response"
    >>>
    >>> # Initialize agent
    >>> agent = NeuroAdaptiveAgent(MockLlm())
    >>>
    >>> # Create decision request
    >>> signals = NeuroSignals(
    ...     dopamine_rpe=0.5,
    ...     serotonin_veto=0.2,
    ...     threat_score=0.3,
    ...     energy_efficiency=0.8,
    ...     prior_confidence=0.7,
    ... )
    >>> request = DecisionRequest(
    ...     raw_proposal={"action": "buy", "symbol": "BTC"},
    ...     neuro_signals=signals,
    ...     risk_tag="medium",
    ... )
    >>>
    >>> # Make decision (async)
    >>> # result = await agent.decide(request)
"""

from __future__ import annotations

from .config import NeuroAdaptiveConfig
from .engine import NeuroAdaptiveAgent, NeuroMetrics
from .state import GateTransition, NeuroGateFsm
from .telemetry import neuro_event_payload
from .types import (
    ControlSignal,
    DecisionRequest,
    DecisionResult,
    LlmClient,
    NeuroGateState,
    NeuroSignals,
)

__all__ = [
    "NeuroSignals",
    "DecisionRequest",
    "DecisionResult",
    "NeuroGateState",
    "ControlSignal",
    "LlmClient",
    "NeuroAdaptiveConfig",
    "NeuroGateFsm",
    "GateTransition",
    "NeuroAdaptiveAgent",
    "NeuroMetrics",
    "neuro_event_payload",
]
