# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Session lifecycle FSM — invariants and enumerated transitions.

Guards the four properties that justify a first-class lifecycle:

1. **Enumerated transitions.** Every cell of the transition table is
   exercised; unknown / inadmissible / terminal transitions all raise
   :class:`InvalidTransitionError`.
2. **Happy path reachability.** The canonical sequence
   ``fit → calibrate → run → complete`` reaches ``COMPLETED``.
3. **Checkpoint / restore branch.** ``run → checkpoint → restore →
   resume → complete`` reaches ``COMPLETED``; intermediate states are
   as declared.
4. **Terminal absorption.** Once in ``COMPLETED`` or ``FAILED``, every
   subsequent transition raises.

Plus envelope round-trip through :func:`to_dict` / :func:`from_dict`
and a Hypothesis property test that any randomly-generated legal
action sequence ends at a declared :class:`SessionState`.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from geosync_hpc.session_fsm import (
    ACTIONS,
    CALIBRATE,
    CHECKPOINT,
    COMPLETE,
    FAIL,
    FIT,
    RESTORE,
    RESUME,
    RUN,
    TERMINAL_STATES,
    TRANSITIONS,
    InvalidTransitionError,
    SessionLifecycle,
    SessionState,
)

# ---------------------------------------------------------------------------
# Construction + invariants
# ---------------------------------------------------------------------------


def test_default_state_is_uninitialized() -> None:
    s = SessionLifecycle()
    assert s.state is SessionState.UNINITIALIZED


def test_lifecycle_is_frozen() -> None:
    s = SessionLifecycle()
    with pytest.raises(Exception):  # FrozenInstanceError
        s.state = SessionState.FITTED  # type: ignore[misc]


def test_actions_constant_matches_transition_table() -> None:
    """Defence in depth: every action referenced in TRANSITIONS must
    appear in ACTIONS. Catches a future rename that drifts one but
    not the other."""
    used = {a for (_, a) in TRANSITIONS}
    assert used <= ACTIONS


def test_terminal_states_have_no_outgoing_transitions() -> None:
    for terminal in TERMINAL_STATES:
        outgoing = [(s, a) for (s, a) in TRANSITIONS if s is terminal]
        assert outgoing == [], f"terminal state {terminal} has outgoing: {outgoing}"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_canonical_happy_path_reaches_completed() -> None:
    s = SessionLifecycle()
    s = s.transition(FIT)
    assert s.state is SessionState.FITTED
    s = s.transition(CALIBRATE)
    assert s.state is SessionState.CALIBRATED
    s = s.transition(RUN)
    assert s.state is SessionState.RUNNING
    s = s.transition(COMPLETE)
    assert s.state is SessionState.COMPLETED
    assert s.is_terminal()


def test_checkpoint_restore_branch_reaches_completed() -> None:
    s = SessionLifecycle()
    for action in (FIT, CALIBRATE, RUN, CHECKPOINT, RESTORE, RESUME, COMPLETE):
        s = s.transition(action)
    assert s.state is SessionState.COMPLETED


# ---------------------------------------------------------------------------
# Failure
# ---------------------------------------------------------------------------


def test_fail_from_every_non_terminal_state() -> None:
    """Failure must be admissible from every non-terminal state."""
    for state in SessionState:
        if state in TERMINAL_STATES:
            continue
        s = SessionLifecycle(state=state)
        s_fail = s.transition(FAIL)
        assert s_fail.state is SessionState.FAILED


def test_failed_is_terminal() -> None:
    s = SessionLifecycle(state=SessionState.FAILED)
    with pytest.raises(InvalidTransitionError):
        s.transition(FIT)
    with pytest.raises(InvalidTransitionError):
        s.transition(FAIL)


def test_completed_is_terminal() -> None:
    s = SessionLifecycle(state=SessionState.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        s.transition(RUN)
    with pytest.raises(InvalidTransitionError):
        s.transition(FAIL)


# ---------------------------------------------------------------------------
# Invalid transitions — every state × every forbidden action
# ---------------------------------------------------------------------------


def test_unknown_action_raises() -> None:
    s = SessionLifecycle()
    with pytest.raises(InvalidTransitionError):
        s.transition("nonsense")


def test_admissible_actions_match_can() -> None:
    """``can`` and ``transition`` must agree on admissibility for every
    (state, action) pair."""
    for state in SessionState:
        for action in ACTIONS:
            s = SessionLifecycle(state=state)
            admissible = s.can(action)
            if admissible:
                s.transition(action)  # must not raise
            else:
                with pytest.raises(InvalidTransitionError):
                    s.transition(action)


def test_run_before_calibrate_is_invalid() -> None:
    s = SessionLifecycle().transition(FIT)
    with pytest.raises(InvalidTransitionError):
        s.transition(RUN)


def test_calibrate_before_fit_is_invalid() -> None:
    s = SessionLifecycle()
    with pytest.raises(InvalidTransitionError):
        s.transition(CALIBRATE)


def test_checkpoint_from_calibrated_is_invalid() -> None:
    s = SessionLifecycle().transition(FIT).transition(CALIBRATE)
    with pytest.raises(InvalidTransitionError):
        s.transition(CHECKPOINT)


def test_inadmissible_action_error_names_exactly_the_admissible_actions() -> None:
    """TEETH: the error's ``allowed:`` hint must name the actions genuinely admissible
    FROM THE CURRENT STATE — never the complement.

    Measured gap this closes: ``tools/mutation_probe.py --only-logic`` showed
    ``session_fsm.py:145`` (``[a for (s, a) in TRANSITIONS if s == self.state]``)
    mutating ``Eq -> NotEq`` and SURVIVING — the whole falsifier killed 0/1 mutants,
    because every existing test asserts only the exception TYPE, never the message.
    Under the mutant the hint lists the actions admissible from every OTHER state, i.e.
    it actively misleads the operator. The expectation below is derived independently in
    test code, so a flipped comparison in the source can no longer agree with it.
    """
    s = SessionLifecycle().transition(FIT)  # state = FITTED
    expected = sorted(a for (st, a) in TRANSITIONS if st == s.state)
    with pytest.raises(InvalidTransitionError) as excinfo:
        s.transition(RUN)  # inadmissible from FITTED
    message = str(excinfo.value)
    assert f"allowed: {expected}" in message, (
        f"InvalidTransitionError must list exactly the actions admissible from "
        f"{s.state.value!r}: expected {expected}; message was: {message}"
    )
    hint = message.split("allowed:", 1)[1]
    assert f"'{RUN}'" not in hint, (
        f"the hint must not advertise {RUN!r}, which is inadmissible from "
        f"{s.state.value!r}; message was: {message}"
    )


def test_resume_without_restore_is_invalid() -> None:
    s = (
        SessionLifecycle()
        .transition(FIT)
        .transition(CALIBRATE)
        .transition(RUN)
        .transition(CHECKPOINT)
    )
    with pytest.raises(InvalidTransitionError):
        s.transition(RESUME)


# ---------------------------------------------------------------------------
# Envelope serialisation
# ---------------------------------------------------------------------------


def test_to_dict_and_from_dict_roundtrip_every_state() -> None:
    for state in SessionState:
        s = SessionLifecycle(state=state)
        restored = SessionLifecycle.from_dict(s.to_dict())
        assert restored == s


def test_from_dict_rejects_missing_state() -> None:
    with pytest.raises(ValueError):
        SessionLifecycle.from_dict({})


def test_from_dict_rejects_non_string_state() -> None:
    with pytest.raises(ValueError):
        SessionLifecycle.from_dict({"state": 1})


def test_from_dict_rejects_unknown_label() -> None:
    with pytest.raises(ValueError):
        SessionLifecycle.from_dict({"state": "not_a_state"})


def test_to_dict_emits_canonical_labels() -> None:
    assert SessionLifecycle().to_dict() == {"state": "uninitialized"}
    assert SessionLifecycle(state=SessionState.COMPLETED).to_dict() == {"state": "completed"}


# ---------------------------------------------------------------------------
# Property: any legal sequence ends at a declared SessionState
# ---------------------------------------------------------------------------


@given(st.lists(st.sampled_from(sorted(ACTIONS)), min_size=0, max_size=20))
@settings(max_examples=300, deadline=None)
def test_random_action_sequences_preserve_invariants(actions: list[str]) -> None:
    """Any action sequence — legal or not — either completes without
    raising and lands in a declared state, or raises InvalidTransitionError
    on the first illegal step. Invariant: the FSM never silently
    produces an undeclared state."""
    s = SessionLifecycle()
    for action in actions:
        try:
            s = s.transition(action)
        except InvalidTransitionError:
            break
        assert isinstance(s.state, SessionState)


# ---------------------------------------------------------------------------
# Transition-table surface audit
# ---------------------------------------------------------------------------


def test_transition_table_has_no_self_loops() -> None:
    for (src, action), dst in TRANSITIONS.items():
        assert src is not dst, f"self-loop at ({src}, {action}); lifecycle must record progress"


def test_every_non_terminal_state_reachable_from_default() -> None:
    """Every non-terminal state must be reachable via the canonical
    happy path + checkpoint branch. Dead states are a design smell."""
    reachable = {SessionState.UNINITIALIZED}
    # Forward flood from the default start.
    frontier = {SessionState.UNINITIALIZED}
    while frontier:
        new_frontier: set[SessionState] = set()
        for state in frontier:
            for (src, _), dst in TRANSITIONS.items():
                if src is state and dst not in reachable:
                    new_frontier.add(dst)
                    reachable.add(dst)
        frontier = new_frontier
    expected = set(SessionState)
    assert reachable == expected, f"unreachable states: {expected - reachable}"
