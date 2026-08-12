# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Formalized system lifecycle model with explicit transitions and invariants."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping, Sequence


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class LifecycleState(str, Enum):
    """Enumerate recognized lifecycle phases for the platform."""

    INIT = "init"
    READY = "ready"
    RUNNING = "running"
    DEGRADED = "degraded"
    RECOVERING = "recovering"
    STOPPED = "stopped"


_ALLOWED_TRANSITIONS: Mapping[LifecycleState, Sequence[LifecycleState]] = {
    LifecycleState.INIT: (LifecycleState.READY,),
    LifecycleState.READY: (LifecycleState.RUNNING, LifecycleState.STOPPED),
    LifecycleState.RUNNING: (
        LifecycleState.DEGRADED,
        LifecycleState.RECOVERING,
        LifecycleState.STOPPED,
    ),
    LifecycleState.DEGRADED: (
        LifecycleState.RECOVERING,
        LifecycleState.STOPPED,
    ),
    LifecycleState.RECOVERING: (
        LifecycleState.RUNNING,
        LifecycleState.DEGRADED,
        LifecycleState.STOPPED,
    ),
    LifecycleState.STOPPED: (),
}

TERMINAL_STATES = frozenset(state for state, allowed in _ALLOWED_TRANSITIONS.items() if not allowed)


@dataclass(frozen=True, slots=True)
class StateTransition:
    """Materialized transition between lifecycle states."""

    from_state: LifecycleState
    to_state: LifecycleState
    reason: str = ""
    timestamp: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", self.reason.strip())


@dataclass(slots=True)
class LifecycleModel:
    """State machine capturing lifecycle, transitions, and invariants."""

    state: LifecycleState = LifecycleState.INIT
    started_at: datetime = field(default_factory=_utc_now)
    transitions: list[StateTransition] = field(default_factory=list)

    def can_transition(self, target: LifecycleState) -> bool:
        """Return True if ``target`` is reachable from the current state."""

        if target == self.state:
            return False
        if self.state in TERMINAL_STATES:
            return False
        return target in _ALLOWED_TRANSITIONS[self.state]

    def transition(
        self,
        target: LifecycleState,
        *,
        reason: str = "",
        at: datetime | None = None,
    ) -> StateTransition:
        """Move the lifecycle to ``target`` if allowed."""

        if target == self.state:
            raise ValueError("no-op transition is not allowed")
        if self.state in TERMINAL_STATES:
            raise ValueError(f"cannot transition from terminal state {self.state.value}")
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"invalid transition {self.state.value} -> {target.value}")

        timestamp = at or _utc_now()
        last_timestamp = self.transitions[-1].timestamp if self.transitions else self.started_at
        if timestamp < last_timestamp:
            raise ValueError("transition timestamp must be monotonic")

        transition = StateTransition(
            from_state=self.state,
            to_state=target,
            reason=reason,
            timestamp=timestamp,
        )
        self.transitions.append(transition)
        self.state = target
        return transition

    def verify_invariants(self) -> None:
        """Validate transition history and lifecycle invariants."""

        last_state = LifecycleState.INIT
        last_timestamp = self.started_at
        for transition in self.transitions:
            if transition.from_state != last_state:
                raise ValueError("transition source does not match current state")
            if transition.to_state not in _ALLOWED_TRANSITIONS[last_state]:
                raise ValueError(
                    f"disallowed transition {last_state.value} -> {transition.to_state.value}"
                )
            if transition.timestamp < last_timestamp:
                raise ValueError("transition timestamps must be monotonic")
            last_state = transition.to_state
            last_timestamp = transition.timestamp

        if self.state != last_state:
            raise ValueError("current state diverges from transition history")

    @property
    def is_terminal(self) -> bool:
        """Whether the lifecycle is in a terminal state."""

        return self.state in TERMINAL_STATES


__all__ = [
    "LifecycleModel",
    "LifecycleState",
    "StateTransition",
    "TERMINAL_STATES",
]
