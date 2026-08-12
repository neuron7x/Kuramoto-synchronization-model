# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Governance FSM — pillar 7 tests."""

from __future__ import annotations

import pytest

from research.systemic_risk.death_conditions import TierTransition
from research.systemic_risk.governance_fsm import (
    INITIAL_STATE,
    PROMOTABLE_LADDER,
    TERMINAL_STATES,
    GovernanceFSM,
    InvalidTransitionError,
)


def _t(action: str, *, fired: tuple[str, ...] = ()) -> TierTransition:
    return TierTransition(action=action, fired_triggers=fired, outcomes=())  # type: ignore[arg-type]


class TestInitialState:
    def test_initial_constructor(self) -> None:
        fsm = GovernanceFSM.initial()
        assert fsm.state == INITIAL_STATE
        assert fsm.history == ()
        assert not fsm.is_terminal

    def test_promotable_ladder_starts_at_idea(self) -> None:
        assert PROMOTABLE_LADDER[0] == "IDEA"

    def test_promotable_ladder_unique(self) -> None:
        assert len(PROMOTABLE_LADDER) == len(set(PROMOTABLE_LADDER))

    def test_terminal_set_contains_rejected(self) -> None:
        assert "REJECTED" in TERMINAL_STATES


class TestKillIsAbsorbing:
    def test_kill_drives_to_rejected(self) -> None:
        fsm = GovernanceFSM.initial()
        fsm = fsm.apply(_t("KILL", fired=("T4_replication_mismatch",)))
        assert fsm.state == "REJECTED"
        assert fsm.is_terminal

    def test_rejected_absorbs_all_subsequent_actions(self) -> None:
        fsm = GovernanceFSM.initial().apply(_t("KILL"))
        for action in ("KILL", "INVALIDATE", "QUARANTINE", "DEMOTE", "STOP", "NONE"):
            after = fsm.apply(_t(action))
            assert after.state == "REJECTED"
            # History grows by one no-op per attempt.
            assert len(after.history) == len(fsm.history) + 1

    def test_kill_from_high_state_still_terminal(self) -> None:
        fsm = (
            GovernanceFSM.initial()
            .promote(target="HYPOTHESIS", evidence_supports=True, reason="seed")
            .promote(target="VALIDATED", evidence_supports=True, reason="climb")
        )
        assert fsm.state == "VALIDATED"
        rejected = fsm.apply(_t("KILL"))
        assert rejected.state == "REJECTED"


class TestInvalidateResetsToIdea:
    def test_invalidate_from_validated(self) -> None:
        fsm = GovernanceFSM.initial().promote(
            target="VALIDATED", evidence_supports=True, reason="climb"
        )
        out = fsm.apply(_t("INVALIDATE", fired=("T2_leakage_positive",)))
        assert out.state == "IDEA"


class TestQuarantine:
    def test_quarantine_from_any_state(self) -> None:
        fsm = GovernanceFSM.initial().promote(target="MEASURED", evidence_supports=True, reason="m")
        out = fsm.apply(_t("QUARANTINE", fired=("T3_parameter_fragility",)))
        assert out.state == "QUARANTINED"

    def test_promote_out_of_quarantine_forbidden(self) -> None:
        fsm = GovernanceFSM.initial().apply(_t("QUARANTINE"))
        with pytest.raises(InvalidTransitionError, match="external sign-off"):
            fsm.promote(target="HYPOTHESIS", evidence_supports=True, reason="x")

    def test_demote_from_quarantine_resets_to_idea(self) -> None:
        fsm = GovernanceFSM.initial().apply(_t("QUARANTINE"))
        out = fsm.apply(_t("DEMOTE"))
        assert out.state == "IDEA"


class TestDemote:
    def test_demote_one_step(self) -> None:
        fsm = GovernanceFSM.initial().promote(target="MEASURED", evidence_supports=True, reason="m")
        out = fsm.apply(_t("DEMOTE"))
        # MEASURED → TESTED_ON_REAL_DATA on the ladder
        assert out.state == "TESTED_ON_REAL_DATA"

    def test_demote_clamps_at_idea(self) -> None:
        fsm = GovernanceFSM.initial()  # state IDEA
        out = fsm.apply(_t("DEMOTE"))
        assert out.state == "IDEA"


class TestStopIsNoOp:
    def test_stop_does_not_change_state(self) -> None:
        fsm = GovernanceFSM.initial().promote(
            target="HYPOTHESIS", evidence_supports=True, reason="h"
        )
        out = fsm.apply(_t("STOP", fired=("T5_data_proxy_invalid",)))
        assert out.state == "HYPOTHESIS"
        # Audit row appended.
        assert out.history[-1].to_state == "HYPOTHESIS"
        assert out.history[-1].action == "STOP"


class TestNoneIsNoOp:
    def test_none_appends_audit_row(self) -> None:
        fsm = GovernanceFSM.initial()
        out = fsm.apply(_t("NONE"))
        assert out.state == "IDEA"
        assert len(out.history) == 1
        assert out.history[0].action == "NONE"


class TestPromote:
    def test_strict_forward_promote_succeeds(self) -> None:
        fsm = GovernanceFSM.initial()
        promoted = fsm.promote(target="HYPOTHESIS", evidence_supports=True, reason="seed")
        assert promoted.state == "HYPOTHESIS"
        assert promoted.history[-1].action == "PROMOTE"

    def test_promote_to_same_state_forbidden(self) -> None:
        fsm = GovernanceFSM.initial()
        with pytest.raises(InvalidTransitionError, match="strictly succeed"):
            fsm.promote(target="IDEA", evidence_supports=True, reason="x")

    def test_promote_backwards_forbidden(self) -> None:
        fsm = GovernanceFSM.initial().promote(
            target="HYPOTHESIS", evidence_supports=True, reason="seed"
        )
        with pytest.raises(InvalidTransitionError, match="strictly succeed"):
            fsm.promote(target="IDEA", evidence_supports=True, reason="back")

    def test_promote_without_evidence_forbidden(self) -> None:
        fsm = GovernanceFSM.initial()
        with pytest.raises(InvalidTransitionError, match="evidence does not support"):
            fsm.promote(target="HYPOTHESIS", evidence_supports=False, reason="x")

    def test_promote_from_rejected_forbidden(self) -> None:
        fsm = GovernanceFSM.initial().apply(_t("KILL"))
        with pytest.raises(InvalidTransitionError, match="terminal state"):
            fsm.promote(target="IDEA", evidence_supports=True, reason="x")

    def test_promote_off_ladder_target_forbidden(self) -> None:
        fsm = GovernanceFSM.initial()
        with pytest.raises(InvalidTransitionError, match="not on the promotable ladder"):
            fsm.promote(target="REJECTED", evidence_supports=True, reason="x")


class TestImmutability:
    def test_apply_returns_new_fsm(self) -> None:
        original = GovernanceFSM.initial()
        new = original.apply(_t("INVALIDATE"))
        assert original.state == "IDEA"
        assert original.history == ()
        assert new is not original
        assert new.history != original.history

    def test_history_is_appended_in_order(self) -> None:
        fsm = GovernanceFSM.initial()
        fsm = fsm.apply(_t("NONE"))
        fsm = fsm.apply(_t("STOP"))
        fsm = fsm.apply(_t("INVALIDATE"))
        assert tuple(r.action for r in fsm.history) == ("NONE", "STOP", "INVALIDATE")
        assert tuple(r.from_state for r in fsm.history) == ("IDEA", "IDEA", "IDEA")
