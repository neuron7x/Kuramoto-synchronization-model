"""Type definitions for the heuristic gate system."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, Mapping, Optional


class GateState(Enum):
    """Finite state machine states for heuristic gate control."""

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


class RiskLevel(Enum):
    """Risk level classification for decisions."""

    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


@dataclass(slots=True)
class HeuristicSignals:
    """Heuristic signals for decision gating.

    Attributes:
        reward_error: Reward prediction error signal (-1.0 to 1.0)
        inhibition_strength: Inhibition signal strength (0.0 to 1.0)
        risk_score: Risk assessment score (0.0 to 1.0)
        energy_efficiency: Energy efficiency metric (0.0 to 1.0)
        prior_confidence: Prior confidence level (0.0 to 1.0)
    """

    reward_error: float | None = None
    inhibition_strength: float | None = None
    risk_score: float | None = None
    energy_efficiency: float | None = None
    prior_confidence: float | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> HeuristicSignals:
        """Create HeuristicSignals from a mapping/dict."""
        return cls(
            reward_error=data.get("reward_error"),
            inhibition_strength=data.get("inhibition_strength"),
            risk_score=data.get("risk_score"),
            energy_efficiency=data.get("energy_efficiency"),
            prior_confidence=data.get("prior_confidence"),
        )

    def as_dict(self) -> Dict[str, Optional[float]]:
        """Convert HeuristicSignals to dictionary representation."""
        return {
            "reward_error": self.reward_error,
            "inhibition_strength": self.inhibition_strength,
            "risk_score": self.risk_score,
            "energy_efficiency": self.energy_efficiency,
            "prior_confidence": self.prior_confidence,
        }


@dataclass(slots=True)
class DecisionRequest:
    """Request for a heuristic gate decision.

    Attributes:
        raw_proposal: The raw trading proposal or decision to evaluate
        signals: Heuristic signals for decision context
        risk_level: Risk level classification
        metadata: Optional additional context metadata
    """

    raw_proposal: Any
    signals: HeuristicSignals
    risk_level: RiskLevel = RiskLevel.MEDIUM
    metadata: Dict[str, Any] | None = None


@dataclass(slots=True)
class DecisionResult:
    """Result of a heuristic gate decision.

    Attributes:
        allowed: Whether the decision/action is allowed
        gate_state: Current FSM gate state
        blended_confidence: Blended confidence score
        control_signal: Control signal that triggered state transition
        reason: Human-readable reason for the decision
        debug: Debug information and telemetry data
    """

    allowed: bool
    gate_state: GateState
    blended_confidence: float
    control_signal: ControlSignal | None
    reason: str
    debug: Dict[str, Any]
