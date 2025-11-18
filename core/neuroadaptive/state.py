"""Finite state machine for neuroadaptive gate control."""

from __future__ import annotations

from dataclasses import dataclass

from .config import NeuroAdaptiveConfig
from .types import ControlSignal, NeuroGateState


@dataclass(slots=True)
class GateTransition:
    """Result of a gate state transition.

    Attributes:
        new_state: The new FSM state after transition
        control_signal: Control signal that triggered the transition
        reason: Human-readable explanation for the transition
    """

    new_state: NeuroGateState
    control_signal: ControlSignal | None
    reason: str


class NeuroGateFsm:
    """Finite state machine for neuroadaptive decision gate control.

    This FSM manages state transitions based on neuromodulator signals
    and risk levels, implementing a sophisticated gating mechanism for
    trading decisions.
    """

    __slots__ = ("_config", "_state")

    def __init__(self, config: NeuroAdaptiveConfig) -> None:
        """Initialize the FSM with configuration.

        Args:
            config: Configuration for threshold values and gate behavior
        """
        self._config = config
        self._state: NeuroGateState = NeuroGateState.REFLEX

    @property
    def state(self) -> NeuroGateState:
        """Get current FSM state."""
        return self._state

    def hard_reset(self) -> None:
        """Reset FSM to initial REFLEX state."""
        self._state = NeuroGateState.REFLEX

    def step(
        self,
        neuro_confidence: float,
        risk_tag: str,
    ) -> GateTransition:
        """Execute one FSM step based on neuro confidence and risk.

        Args:
            neuro_confidence: Confidence score from neuromodulator signals
            risk_tag: Risk category (low/medium/high/critical)

        Returns:
            GateTransition describing the state change
        """
        t = self._config.gate_thresholds
        state = self._state

        # Clamp confidence to [0, 1]
        c = max(0.0, min(1.0, neuro_confidence))
        risk = risk_tag.lower()

        # Hard block: confidence too low
        if c <= t["hard_block"]:
            self._state = NeuroGateState.INHIBITED
            return GateTransition(
                new_state=self._state,
                control_signal=ControlSignal.INHIBIT,
                reason=f"neuro_confidence={c:.2f} ≤ hard_block",
            )

        # Soft block: confidence low, needs review
        if c <= t["soft_block"]:
            self._state = NeuroGateState.ARMED
            return GateTransition(
                new_state=self._state,
                control_signal=ControlSignal.ARM,
                reason=f"neuro_confidence={c:.2f} ≤ soft_block, ARMED",
            )

        # Hard allow: high confidence
        if c >= t["hard_allow"]:
            if risk == "critical":
                # Critical risk always requires explicit release
                self._state = NeuroGateState.ARMED
                return GateTransition(
                    new_state=self._state,
                    control_signal=ControlSignal.ARM,
                    reason="critical risk, require explicit RELEASE",
                )
            self._state = NeuroGateState.RELEASED
            return GateTransition(
                new_state=self._state,
                control_signal=ControlSignal.RELEASE,
                reason=f"neuro_confidence={c:.2f} ≥ hard_allow",
            )

        # Soft allow: moderate confidence
        if c >= t["soft_allow"]:
            if risk in ("low", "medium"):
                self._state = NeuroGateState.RELEASED
                return GateTransition(
                    new_state=self._state,
                    control_signal=ControlSignal.RELEASE,
                    reason="soft_allow & low/medium risk",
                )
            self._state = NeuroGateState.ARMED
            return GateTransition(
                new_state=self._state,
                control_signal=ControlSignal.ARM,
                reason="soft_allow & high risk → ARMED",
            )

        # If inhibited, stay inhibited until override
        if state == NeuroGateState.INHIBITED:
            return GateTransition(
                new_state=self._state,
                control_signal=None,
                reason="INHIBITED → stay until override",
            )

        # Default: middle band → ARMED
        self._state = NeuroGateState.ARMED
        return GateTransition(
            new_state=self._state,
            control_signal=ControlSignal.ARM,
            reason="middle band → ARMED",
        )

    def apply_external_signal(self, signal: ControlSignal) -> GateTransition:
        """Apply an external control signal to the FSM.

        Args:
            signal: External control signal to apply

        Returns:
            GateTransition describing the state change
        """
        if signal == ControlSignal.RESET:
            self._state = NeuroGateState.REFLEX
            return GateTransition(
                new_state=self._state,
                control_signal=signal,
                reason="external RESET",
            )

        if signal == ControlSignal.OVERRIDE_ALLOW:
            self._state = NeuroGateState.OVERRIDDEN
            return GateTransition(
                new_state=self._state,
                control_signal=signal,
                reason="OVERRIDE_ALLOW",
            )

        if signal == ControlSignal.OVERRIDE_BLOCK:
            self._state = NeuroGateState.OVERRIDDEN
            return GateTransition(
                new_state=self._state,
                control_signal=signal,
                reason="OVERRIDE_BLOCK",
            )

        if signal == ControlSignal.INHIBIT:
            self._state = NeuroGateState.INHIBITED
        elif signal == ControlSignal.ARM:
            self._state = NeuroGateState.ARMED
        elif signal == ControlSignal.RELEASE:
            self._state = NeuroGateState.RELEASED

        return GateTransition(
            new_state=self._state,
            control_signal=signal,
            reason="manual soft control",
        )
