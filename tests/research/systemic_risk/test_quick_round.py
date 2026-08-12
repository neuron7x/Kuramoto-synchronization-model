# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Quick-round ergonomic-API tests."""

from __future__ import annotations

from research.systemic_risk.governance_fsm import GovernanceFSM
from research.systemic_risk.quick_round import quick_round


class TestQuickRound:
    def test_all_none_yields_none_action(self) -> None:
        out = quick_round(fsm_before=GovernanceFSM.initial())
        assert out.transition.action == "NONE"
        assert out.fsm_after.state == "IDEA"

    def test_replication_mismatch_drives_kill(self) -> None:
        out = quick_round(
            fsm_before=GovernanceFSM.initial(),
            replication_matched=False,
        )
        assert out.transition.action == "KILL"
        assert out.fsm_after.state == "REJECTED"

    def test_leakage_detected_drives_invalidate(self) -> None:
        fsm = GovernanceFSM.initial().promote(
            target="HYPOTHESIS", evidence_supports=True, reason="seed"
        )
        out = quick_round(fsm_before=fsm, leakage_detected=True)
        assert out.transition.action == "INVALIDATE"
        assert out.fsm_after.state == "IDEA"

    def test_fragile_drives_quarantine(self) -> None:
        out = quick_round(fsm_before=GovernanceFSM.initial(), fragile=True)
        assert out.transition.action == "QUARANTINE"
        assert out.fsm_after.state == "QUARANTINED"

    def test_losing_paths_drives_demote(self) -> None:
        fsm = GovernanceFSM.initial().promote(target="MEASURED", evidence_supports=True, reason="m")
        out = quick_round(fsm_before=fsm, losing_paths=("naive_baseline",))
        assert out.transition.action == "DEMOTE"
        assert out.fsm_after.state == "TESTED_ON_REAL_DATA"

    def test_firewall_failure_drives_stop(self) -> None:
        out = quick_round(
            fsm_before=GovernanceFSM.initial(),
            firewall_passed_all=False,
        )
        assert out.transition.action == "STOP"
        # STOP does not change state.
        assert out.fsm_after.state == "IDEA"

    def test_clean_round_keeps_state(self) -> None:
        fsm = GovernanceFSM.initial()
        out = quick_round(
            fsm_before=fsm,
            firewall_passed_all=True,
            leakage_detected=False,
            losing_paths=(),
            fragile=False,
            replication_matched=True,
        )
        assert out.transition.action == "NONE"
        assert out.fsm_after.state == "IDEA"

    def test_kill_dominates_demote_via_quick(self) -> None:
        # T1 (DEMOTE from losing_paths) AND T4 (KILL from
        # replication_matched=False) both fire — KILL wins.
        out = quick_round(
            fsm_before=GovernanceFSM.initial(),
            losing_paths=("p1",),
            replication_matched=False,
        )
        assert out.transition.action == "KILL"
        assert out.fsm_after.state == "REJECTED"

    def test_partial_inputs_are_safe(self) -> None:
        # Only the evidence channels you actually evaluated should
        # fire triggers. Setting only firewall_passed_all=True must
        # not cause spurious DEMOTE/INVALIDATE.
        out = quick_round(
            fsm_before=GovernanceFSM.initial(),
            firewall_passed_all=True,
        )
        assert out.transition.action == "NONE"
        assert out.fsm_after.state == "IDEA"

    def test_iterative_research_loop_pattern(self) -> None:
        # The canonical research-loop pattern: thread the FSM through
        # successive rounds without rebuilding inputs each time.
        fsm = GovernanceFSM.initial()
        for _ in range(3):
            out = quick_round(
                fsm_before=fsm,
                firewall_passed_all=True,
                leakage_detected=False,
                losing_paths=(),
            )
            fsm = out.fsm_after
        assert len(fsm.history) == 3
        assert fsm.state == "IDEA"
