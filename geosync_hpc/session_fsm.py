# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""BacktesterCAL lifecycle — explicit finite-state machine.

A backtest session moves through a small number of qualitatively
different states (untrained model, fitted quantiles, calibrated
conformal, running loop, checkpointed, restored, completed, failed).
The existing ``BacktesterCAL`` encodes these phases implicitly: a
caller who invokes ``run`` before ``calibrate_conformal`` gets a
cryptic ``KeyError`` deep in the loop; one who invokes ``calibrate``
before ``fit_quantiles`` fits on ``None``; a restore that lands the
session into an impossible state (``COMPLETED → RUNNING``) fails
silently.

This module makes the lifecycle explicit, testable, and snapshotable.
It does *not* replace ``BacktesterCAL`` — it sits next to it as a
companion state machine that the harness will route every public
operation through in a follow-up PR. Keeping the FSM isolated lets
it fail-close on its own invariant tests first.

Design choices:

* **Eight states, ten transitions.** The full transition table is a
  single public constant (:data:`TRANSITIONS`); unit tests enumerate
  every cell.
* **Terminal states are absorbing.** ``COMPLETED`` and ``FAILED``
  accept no further transitions — attempting one raises
  :class:`InvalidTransitionError` with a helpful message.
* **Failure is first-class.** ``fail`` is a valid action from every
  non-terminal state; observability matters more than aesthetic purity.
* **Serialisable.** ``SessionLifecycle.to_dict`` / ``from_dict`` round-
  trip cleanly into a :mod:`geosync_hpc.runtime_state` envelope
  payload without losing information.

Rejecting heavier formal-methods machinery (TLA+, Alloy) is intentional
for this scope. A property test that exercises every transition cell
is sufficient evidence at the Task 5 scope; a model-checker becomes
worthwhile when the transition graph grows non-trivial branching.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Final, Mapping


class SessionState(str, Enum):
    """Lifecycle state of a backtest session.

    Inherits from ``str`` so that JSON encoding of the envelope payload
    yields readable labels without a custom encoder.
    """

    UNINITIALIZED = "uninitialized"
    FITTED = "fitted"
    CALIBRATED = "calibrated"
    RUNNING = "running"
    CHECKPOINTED = "checkpointed"
    RESTORED = "restored"
    COMPLETED = "completed"
    FAILED = "failed"


# Actions are plain strings — avoids a second enum that would have to
# be kept synchronised with a string vocabulary at the envelope edge.
FIT: Final[str] = "fit"
CALIBRATE: Final[str] = "calibrate"
RUN: Final[str] = "run"
CHECKPOINT: Final[str] = "checkpoint"
RESTORE: Final[str] = "restore"
RESUME: Final[str] = "resume"
COMPLETE: Final[str] = "complete"
FAIL: Final[str] = "fail"

ACTIONS: Final[frozenset[str]] = frozenset(
    {FIT, CALIBRATE, RUN, CHECKPOINT, RESTORE, RESUME, COMPLETE, FAIL}
)

TERMINAL_STATES: Final[frozenset[SessionState]] = frozenset(
    {SessionState.COMPLETED, SessionState.FAILED}
)

TRANSITIONS: Final[dict[tuple[SessionState, str], SessionState]] = {
    # Happy path:
    (SessionState.UNINITIALIZED, FIT): SessionState.FITTED,
    (SessionState.FITTED, CALIBRATE): SessionState.CALIBRATED,
    (SessionState.CALIBRATED, RUN): SessionState.RUNNING,
    (SessionState.RUNNING, COMPLETE): SessionState.COMPLETED,
    # Checkpoint / restore branch:
    (SessionState.RUNNING, CHECKPOINT): SessionState.CHECKPOINTED,
    (SessionState.CHECKPOINTED, RESTORE): SessionState.RESTORED,
    (SessionState.RESTORED, RESUME): SessionState.RUNNING,
    # Failure is admissible from any non-terminal state:
    (SessionState.FITTED, FAIL): SessionState.FAILED,
    (SessionState.CALIBRATED, FAIL): SessionState.FAILED,
    (SessionState.RUNNING, FAIL): SessionState.FAILED,
    (SessionState.CHECKPOINTED, FAIL): SessionState.FAILED,
    (SessionState.RESTORED, FAIL): SessionState.FAILED,
    (SessionState.UNINITIALIZED, FAIL): SessionState.FAILED,
}


class InvalidTransitionError(Exception):
    """Attempted action is not admissible from the current state."""


@dataclass(frozen=True)
class SessionLifecycle:
    """Immutable lifecycle snapshot.

    Evolve by calling :meth:`transition`, which returns a new instance
    (the old instance is unchanged). This keeps rollback trivial and
    matches the ``runtime_state`` envelope's "dump every field"
    contract.
    """

    state: SessionState = SessionState.UNINITIALIZED

    def can(self, action: str) -> bool:
        """Return True if ``action`` is admissible from the current
        state. Unknown actions return False (not raise)."""
        return (self.state, action) in TRANSITIONS

    def transition(self, action: str) -> SessionLifecycle:
        """Return a new lifecycle after applying ``action``.

        Raises
        ------
        InvalidTransitionError
            The action is unknown, or not admissible from the current
            state (including all attempts to leave a terminal state).
        """
        if action not in ACTIONS:
            raise InvalidTransitionError(
                f"unknown action {action!r}; valid actions: {sorted(ACTIONS)}"
            )
        if self.state in TERMINAL_STATES:
            raise InvalidTransitionError(
                f"cannot transition from terminal state {self.state.value!r}; "
                f"attempted action {action!r}"
            )
        key = (self.state, action)
        if key not in TRANSITIONS:
            allowed = [a for (s, a) in TRANSITIONS if s == self.state]
            raise InvalidTransitionError(
                f"action {action!r} not admissible from {self.state.value!r}; "
                f"allowed: {sorted(allowed)}"
            )
        return replace(self, state=TRANSITIONS[key])

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    # --- envelope serialisation ------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Canonical JSON-safe dict, pairable with
        :mod:`geosync_hpc.runtime_state`."""
        return {"state": self.state.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SessionLifecycle:
        """Inverse of :meth:`to_dict`.

        Raises
        ------
        ValueError
            ``state`` missing, not a string, or not a recognised
            :class:`SessionState` label.
        """
        if "state" not in payload:
            raise ValueError(f"payload missing 'state': {payload!r}")
        raw = payload["state"]
        if not isinstance(raw, str):
            raise ValueError(f"'state' must be a string, got {type(raw).__name__}")
        try:
            state = SessionState(raw)
        except ValueError as exc:
            raise ValueError(f"unknown SessionState label {raw!r}") from exc
        return cls(state=state)
