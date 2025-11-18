"""Type definitions for the neuroadaptive decision system."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, Mapping, Optional, Protocol


class NeuroGateState(Enum):
    """Finite state machine states for neuroadaptive gate control."""

    REFLEX = auto()
    INHIBITED = auto()
    ARMED = auto()
    RELEASED = auto()
    OVERRIDDEN = auto()


class ControlSignal(Enum):
    """Control signals for gate state transitions."""

    INHIBIT = auto()
    ARM = auto()
    RELEASE = auto()
    RESET = auto()
    OVERRIDE_ALLOW = auto()
    OVERRIDE_BLOCK = auto()


@dataclass(slots=True)
class NeuroSignals:
    """Neuromodulator-inspired signals for decision making.

    Attributes:
        dopamine_rpe: Reward prediction error signal (-1.0 to 1.0)
        serotonin_veto: Veto/inhibition signal (0.0 to 1.0)
        threat_score: Threat assessment score (0.0 to 1.0)
        energy_efficiency: Energy efficiency metric (0.0 to 1.0)
        prior_confidence: Prior confidence level (0.0 to 1.0)
    """

    dopamine_rpe: float | None = None
    serotonin_veto: float | None = None
    threat_score: float | None = None
    energy_efficiency: float | None = None
    prior_confidence: float | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> NeuroSignals:
        """Create NeuroSignals from a mapping/dict."""
        return cls(
            dopamine_rpe=data.get("dopamine_rpe"),
            serotonin_veto=data.get("serotonin_veto"),
            threat_score=data.get("threat_score"),
            energy_efficiency=data.get("energy_efficiency"),
            prior_confidence=data.get("prior_confidence"),
        )

    def as_dict(self) -> Dict[str, Optional[float]]:
        """Convert NeuroSignals to dictionary representation."""
        return {
            "dopamine_rpe": self.dopamine_rpe,
            "serotonin_veto": self.serotonin_veto,
            "threat_score": self.threat_score,
            "energy_efficiency": self.energy_efficiency,
            "prior_confidence": self.prior_confidence,
        }


@dataclass(slots=True)
class DecisionRequest:
    """Request for a neuroadaptive decision.

    Attributes:
        raw_proposal: The raw trading proposal or decision to evaluate
        neuro_signals: Neuromodulator signals for decision context
        risk_tag: Risk category (low/medium/high/critical)
        metadata: Optional additional context metadata
    """

    raw_proposal: Any
    neuro_signals: NeuroSignals
    risk_tag: str = "medium"
    metadata: Dict[str, Any] | None = None


@dataclass(slots=True)
class DecisionResult:
    """Result of a neuroadaptive decision.

    Attributes:
        allowed: Whether the decision/action is allowed
        gate_state: Current FSM gate state
        blended_confidence: Blended confidence score
        control_signal: Control signal that triggered state transition
        reason: Human-readable reason for the decision
        debug: Debug information and telemetry data
    """

    allowed: bool
    gate_state: NeuroGateState
    blended_confidence: float
    control_signal: ControlSignal | None
    reason: str
    debug: Dict[str, Any]


class LlmClient(Protocol):
    """Protocol for LLM client integration."""

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        """Generate completion from LLM."""
        ...
