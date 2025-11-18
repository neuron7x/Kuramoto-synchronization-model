"""Finite state machine for heuristic gate control with table-driven transitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from .config import HeuristicGateConfig
from .types import ControlSignal, GateState


@dataclass(slots=True)
class GateTransition:
    """Result of a gate state transition.

    Attributes:
        new_state: The new FSM state after transition
        control_signal: Control signal that triggered the transition
        reason: Human-readable explanation for the transition
    """

    new_state: GateState
    control_signal: ControlSignal | None
    reason: str


class HeuristicGateFsm:
    """Table-driven finite state machine for heuristic gate control.

    This FSM uses an explicit transition table to manage state changes,
    with validation to ensure all states are reachable from REFLEX.
    """

    __slots__ = ("_config", "_state")

    # Explicit transition table: (current_state, signal) -> new_state
    _TABLE: Dict[Tuple[GateState, ControlSignal], GateState] = {
        # From REFLEX
        (GateState.REFLEX, ControlSignal.INHIBIT): GateState.INHIBITED,
        (GateState.REFLEX, ControlSignal.ARM): GateState.ARMED,
        (GateState.REFLEX, ControlSignal.RELEASE): GateState.RELEASED,
        (GateState.REFLEX, ControlSignal.RESET): GateState.REFLEX,
        (GateState.REFLEX, ControlSignal.OVERRIDE_ALLOW): GateState.OVERRIDDEN,
        (GateState.REFLEX, ControlSignal.OVERRIDE_BLOCK): GateState.OVERRIDDEN,
        # From INHIBITED
        (GateState.INHIBITED, ControlSignal.INHIBIT): GateState.INHIBITED,
        (GateState.INHIBITED, ControlSignal.ARM): GateState.ARMED,
        (GateState.INHIBITED, ControlSignal.RELEASE): GateState.ARMED,
        (GateState.INHIBITED, ControlSignal.RESET): GateState.REFLEX,
        (GateState.INHIBITED, ControlSignal.OVERRIDE_ALLOW): GateState.OVERRIDDEN,
        (GateState.INHIBITED, ControlSignal.OVERRIDE_BLOCK): GateState.OVERRIDDEN,
        # From ARMED
        (GateState.ARMED, ControlSignal.INHIBIT): GateState.INHIBITED,
        (GateState.ARMED, ControlSignal.ARM): GateState.ARMED,
        (GateState.ARMED, ControlSignal.RELEASE): GateState.RELEASED,
        (GateState.ARMED, ControlSignal.RESET): GateState.REFLEX,
        (GateState.ARMED, ControlSignal.OVERRIDE_ALLOW): GateState.OVERRIDDEN,
        (GateState.ARMED, ControlSignal.OVERRIDE_BLOCK): GateState.OVERRIDDEN,
        # From RELEASED
        (GateState.RELEASED, ControlSignal.INHIBIT): GateState.INHIBITED,
        (GateState.RELEASED, ControlSignal.ARM): GateState.ARMED,
        (GateState.RELEASED, ControlSignal.RELEASE): GateState.RELEASED,
        (GateState.RELEASED, ControlSignal.RESET): GateState.REFLEX,
        (GateState.RELEASED, ControlSignal.OVERRIDE_ALLOW): GateState.OVERRIDDEN,
        (GateState.RELEASED, ControlSignal.OVERRIDE_BLOCK): GateState.OVERRIDDEN,
        # From OVERRIDDEN
        (GateState.OVERRIDDEN, ControlSignal.RESET): GateState.REFLEX,
        (GateState.OVERRIDDEN, ControlSignal.INHIBIT): GateState.OVERRIDDEN,
        (GateState.OVERRIDDEN, ControlSignal.ARM): GateState.OVERRIDDEN,
        (GateState.OVERRIDDEN, ControlSignal.RELEASE): GateState.OVERRIDDEN,
        (GateState.OVERRIDDEN, ControlSignal.OVERRIDE_ALLOW): GateState.OVERRIDDEN,
        (GateState.OVERRIDDEN, ControlSignal.OVERRIDE_BLOCK): GateState.OVERRIDDEN,
    }

    def __init__(self, config: HeuristicGateConfig) -> None:
        """Initialize FSM with configuration and validate transition table.

        Args:
            config: Configuration for gate behavior

        Raises:
            AssertionError: If transition table is invalid or states unreachable
        """
        self._config = config
        self._state: GateState = GateState.REFLEX
        self._validate_table()

    @property
    def state(self) -> GateState:
        """Get current FSM state."""
        return self._state

    def hard_reset(self) -> None:
        """Reset FSM to initial REFLEX state."""
        self._state = GateState.REFLEX

    def apply(self, signal: ControlSignal, reason: str) -> GateTransition:
        """Apply control signal to FSM and transition to new state.

        Args:
            signal: Control signal to apply
            reason: Reason for applying this signal

        Returns:
            GateTransition describing the state change
        """
        key = (self._state, signal)
        new_state = self._TABLE.get(key, self._state)
        self._state = new_state
        return GateTransition(
            new_state=new_state,
            control_signal=signal,
            reason=reason,
        )

    def _validate_table(self) -> None:
        """Validate transition table integrity.

        Checks:
        1. All table entries point to valid GateStates
        2. All states are reachable from REFLEX

        Raises:
            AssertionError: If validation fails
        """
        # Validate all targets are GateState instances
        for state in GateState:
            for signal in ControlSignal:
                key = (state, signal)
                if key in self._TABLE:
                    if not isinstance(self._TABLE[key], GateState):
                        raise AssertionError(f"invalid target for {key}")

        # Validate all states are reachable from REFLEX
        reachable = self._reachable_states(GateState.REFLEX)
        missing = set(GateState) - reachable
        if missing:
            raise AssertionError(f"unreachable states: {missing}")

    @classmethod
    def _reachable_states(cls, start: GateState) -> Set[GateState]:
        """Compute set of states reachable from start state.

        Args:
            start: Starting state

        Returns:
            Set of reachable states including start
        """
        visited: Set[GateState] = set()
        stack: List[GateState] = [start]
        while stack:
            st = stack.pop()
            if st in visited:
                continue
            visited.add(st)
            for (s, _), t in cls._TABLE.items():
                if s == st and t not in visited:
                    stack.append(t)
        return visited
