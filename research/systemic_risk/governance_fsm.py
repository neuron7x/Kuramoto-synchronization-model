# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Governance FSM — pillar 7 of the Canonical Seven.

Operationalises § 7 of the canonical-7 charter. Every claim's lifecycle
is a finite-state machine with an explicit terminal absorbing state
``REJECTED``. The FSM is fail-closed: only registered transitions
fire, illegal transitions raise :class:`InvalidTransitionError`, and
once a claim hits ``REJECTED`` it cannot be resurrected.

State graph::

    IDEA → HYPOTHESIS → INSTRUMENTED → TESTED_ON_SYNTHETIC
         ↓            ↓                ↓
         └────────────┴────────────────┴──→ TESTED_ON_REAL_DATA
                                            ↓
                                            MEASURED → REPLICATED → VALIDATED

    Any state ──KILL──→ REJECTED        (terminal, absorbing)
    Any state ──INVALIDATE──→ IDEA      (reset, evidence struck)
    Any state ──QUARANTINE──→ QUARANTINED  (frozen pending external review)
    Any state ──DEMOTE──→ previous tier (one step back along the ladder)
    Any state ──STOP──→ state unchanged (run-pipeline halted, claim untouched)
    Any state ──NONE──→ state unchanged

The FSM consumes :class:`TierTransition` from
:mod:`research.systemic_risk.death_conditions` as the event vocabulary.
Pure-function API. No I/O. Frozen, immutable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from .death_conditions import TierAction, TierTransition

__all__ = [
    "GovernanceState",
    "GovernanceTransitionRecord",
    "GovernanceFSM",
    "InvalidTransitionError",
    "PROMOTABLE_LADDER",
    "TERMINAL_STATES",
    "INITIAL_STATE",
]


GovernanceState = Literal[
    "IDEA",
    "HYPOTHESIS",
    "INSTRUMENTED",
    "TESTED_ON_SYNTHETIC",
    "TESTED_ON_REAL_DATA",
    "MEASURED",
    "REPLICATED",
    "VALIDATED",
    "QUARANTINED",
    "REJECTED",
]


PROMOTABLE_LADDER: Final[tuple[GovernanceState, ...]] = (
    "IDEA",
    "HYPOTHESIS",
    "INSTRUMENTED",
    "TESTED_ON_SYNTHETIC",
    "TESTED_ON_REAL_DATA",
    "MEASURED",
    "REPLICATED",
    "VALIDATED",
)


TERMINAL_STATES: Final[frozenset[GovernanceState]] = frozenset({"REJECTED"})


INITIAL_STATE: Final[GovernanceState] = "IDEA"


class InvalidTransitionError(ValueError):
    """Raised when a transition from the current state is forbidden.

    Examples include attempting to promote out of ``REJECTED`` or
    attempting to promote to an off-ladder target.
    """


@dataclass(frozen=True, slots=True)
class GovernanceTransitionRecord:
    """Single transition's full audit trail entry.

    Attributes
    ----------
    from_state, to_state
        States before and after the transition.
    action
        The :class:`death_conditions.TierAction` that caused the
        transition, or ``"PROMOTE"`` for a manual promotion.
    fired_triggers
        Names of triggers that fired in the originating
        :class:`TierTransition`. Empty tuple for manual promotions.
    reason
        Free-form audit note.
    """

    from_state: GovernanceState
    to_state: GovernanceState
    action: TierAction | Literal["PROMOTE"]
    fired_triggers: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class GovernanceFSM:
    """Finite-state machine for one claim's tier lifecycle.

    Frozen by design — every transition returns a *new* FSM rather
    than mutating in place. The :attr:`history` tuple is the
    append-only audit trail of every transition ever applied.
    """

    state: GovernanceState
    history: tuple[GovernanceTransitionRecord, ...] = ()

    @classmethod
    def initial(cls) -> "GovernanceFSM":
        """Construct an FSM at the canonical entry state ``IDEA``."""
        return cls(state=INITIAL_STATE, history=())

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def apply(self, transition: TierTransition) -> "GovernanceFSM":
        """Apply a :class:`TierTransition` from the death engine.

        Mapping rules:

        * ``KILL``        → ``REJECTED`` (terminal)
        * ``INVALIDATE``  → ``IDEA``     (reset, evidence struck)
        * ``QUARANTINE``  → ``QUARANTINED``
        * ``DEMOTE``      → previous step on :data:`PROMOTABLE_LADDER`;
                            ``IDEA`` stays at ``IDEA`` (cannot demote
                            below the floor).
        * ``STOP``        → state unchanged (run-pipeline halt only)
        * ``NONE``        → state unchanged

        ``REJECTED`` is absorbing: every apply returns the same FSM
        with an audit-only record noting the no-op.
        """
        if self.state == "REJECTED":
            return self._note_no_op(
                action=transition.action,
                fired_triggers=transition.fired_triggers,
                reason="REJECTED is absorbing — no further transitions",
            )

        action = transition.action
        if action == "KILL":
            return self._with_transition(
                to_state="REJECTED",
                action="KILL",
                fired_triggers=transition.fired_triggers,
                reason="KILL trigger fired — claim REJECTED (terminal)",
            )
        if action == "INVALIDATE":
            return self._with_transition(
                to_state="IDEA",
                action="INVALIDATE",
                fired_triggers=transition.fired_triggers,
                reason="INVALIDATE — reset to IDEA, evidence struck",
            )
        if action == "QUARANTINE":
            return self._with_transition(
                to_state="QUARANTINED",
                action="QUARANTINE",
                fired_triggers=transition.fired_triggers,
                reason="QUARANTINE — frozen pending external review",
            )
        if action == "DEMOTE":
            target = self._demote_target()
            return self._with_transition(
                to_state=target,
                action="DEMOTE",
                fired_triggers=transition.fired_triggers,
                reason=f"DEMOTE — one step back to {target}",
            )
        if action == "STOP":
            return self._note_no_op(
                action="STOP",
                fired_triggers=transition.fired_triggers,
                reason="STOP — run halted, claim state unchanged",
            )
        # NONE
        return self._note_no_op(
            action="NONE",
            fired_triggers=transition.fired_triggers,
            reason="NONE — no triggers fired",
        )

    def promote(
        self,
        *,
        target: GovernanceState,
        evidence_supports: bool,
        reason: str,
    ) -> "GovernanceFSM":
        """Manually promote the claim to a higher tier on the ladder.

        Contract:

        * ``self.state`` and ``target`` both lie on
          :data:`PROMOTABLE_LADDER`.
        * ``target`` strictly succeeds ``self.state`` on the ladder
          (no sideways or backwards "promotions").
        * ``evidence_supports`` is ``True``; otherwise
          :class:`InvalidTransitionError`.
        * ``self.state`` is not in :data:`TERMINAL_STATES`.

        ``QUARANTINED`` is *not* on the promotable ladder — escape
        from quarantine requires an external sign-off path that this
        module does not encode (it is enforced at a higher layer).
        """
        if self.state in TERMINAL_STATES:
            raise InvalidTransitionError(f"cannot promote from terminal state {self.state!r}")
        if self.state == "QUARANTINED":
            raise InvalidTransitionError(
                "promotion out of QUARANTINED requires external sign-off; "
                "this FSM does not encode that path"
            )
        if self.state not in PROMOTABLE_LADDER:
            raise InvalidTransitionError(
                f"current state {self.state!r} not on the promotable ladder"
            )
        if target not in PROMOTABLE_LADDER:
            raise InvalidTransitionError(f"target {target!r} not on the promotable ladder")
        from_idx = PROMOTABLE_LADDER.index(self.state)
        to_idx = PROMOTABLE_LADDER.index(target)
        if to_idx <= from_idx:
            raise InvalidTransitionError(
                f"target {target!r} does not strictly succeed current {self.state!r} on the ladder"
            )
        if not evidence_supports:
            raise InvalidTransitionError(
                f"evidence does not support promotion {self.state!r} → {target!r}; refused"
            )
        return self._with_transition(
            to_state=target,
            action="PROMOTE",
            fired_triggers=(),
            reason=reason,
        )

    # -----------------------------------------------------------------
    # Internal helpers (frozen-aware)
    # -----------------------------------------------------------------

    def _with_transition(
        self,
        *,
        to_state: GovernanceState,
        action: TierAction | Literal["PROMOTE"],
        fired_triggers: tuple[str, ...],
        reason: str,
    ) -> "GovernanceFSM":
        record = GovernanceTransitionRecord(
            from_state=self.state,
            to_state=to_state,
            action=action,
            fired_triggers=fired_triggers,
            reason=reason,
        )
        return GovernanceFSM(state=to_state, history=self.history + (record,))

    def _note_no_op(
        self,
        *,
        action: TierAction,
        fired_triggers: tuple[str, ...],
        reason: str,
    ) -> "GovernanceFSM":
        """Append a no-op record so the audit trail is complete."""
        record = GovernanceTransitionRecord(
            from_state=self.state,
            to_state=self.state,
            action=action,
            fired_triggers=fired_triggers,
            reason=reason,
        )
        return GovernanceFSM(state=self.state, history=self.history + (record,))

    def _demote_target(self) -> GovernanceState:
        """Compute the one-step demotion target, clamping at IDEA."""
        if self.state == "QUARANTINED":
            # Demote-from-quarantine resets to IDEA: the quarantine has
            # not been cleared and the evidence base is now untrusted.
            return "IDEA"
        if self.state not in PROMOTABLE_LADDER:
            return INITIAL_STATE
        idx = PROMOTABLE_LADDER.index(self.state)
        if idx == 0:
            # Already at IDEA; clamp.
            return "IDEA"
        return PROMOTABLE_LADDER[idx - 1]
