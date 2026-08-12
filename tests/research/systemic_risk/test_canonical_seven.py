# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Canonical-Seven orchestrator tests — end-to-end pipeline composition."""

from __future__ import annotations

from dataclasses import dataclass

from research.systemic_risk.canonical_seven import (
    CanonicalSevenInputs,
    CanonicalSevenOutcome,
    run_canonical_seven,
)
from research.systemic_risk.governance_fsm import GovernanceFSM


@dataclass
class _Ladder:
    losing_paths: tuple[str, ...]


@dataclass
class _Leakage:
    detected: bool


@dataclass
class _Fragility:
    fragile: bool


@dataclass
class _Replication:
    matched: bool


@dataclass
class _Firewall:
    passed_all: bool


class TestCanonicalSevenOrchestrator:
    def test_all_clean_yields_none_action_and_unchanged_state(self) -> None:
        inputs = CanonicalSevenInputs(
            firewall=_Firewall(passed_all=True),
            leakage=_Leakage(detected=False),
            ladder=_Ladder(losing_paths=()),
            fragility=_Fragility(fragile=False),
            replication=_Replication(matched=True),
        )
        fsm = GovernanceFSM.initial()
        out = run_canonical_seven(inputs=inputs, fsm_before=fsm)
        assert isinstance(out, CanonicalSevenOutcome)
        assert out.transition.action == "NONE"
        assert out.fsm_after.state == "IDEA"

    def test_kill_path_drives_to_rejected(self) -> None:
        inputs = CanonicalSevenInputs(
            replication=_Replication(matched=False),
        )
        fsm = GovernanceFSM.initial()
        out = run_canonical_seven(inputs=inputs, fsm_before=fsm)
        assert out.transition.action == "KILL"
        assert out.fsm_after.state == "REJECTED"
        assert out.fsm_after.is_terminal

    def test_kill_dominates_demote(self) -> None:
        # T1 (DEMOTE) AND T4 (KILL) both fire — KILL must win.
        inputs = CanonicalSevenInputs(
            ladder=_Ladder(losing_paths=("naive",)),
            replication=_Replication(matched=False),
        )
        fsm = GovernanceFSM.initial()
        out = run_canonical_seven(inputs=inputs, fsm_before=fsm)
        assert out.transition.action == "KILL"
        assert "T1_baseline_dominance" in out.transition.fired_triggers
        assert "T4_replication_mismatch" in out.transition.fired_triggers
        assert out.fsm_after.state == "REJECTED"

    def test_invalidate_resets_to_idea(self) -> None:
        inputs = CanonicalSevenInputs(leakage=_Leakage(detected=True))
        fsm = GovernanceFSM.initial().promote(
            target="HYPOTHESIS", evidence_supports=True, reason="seed"
        )
        out = run_canonical_seven(inputs=inputs, fsm_before=fsm)
        assert out.transition.action == "INVALIDATE"
        assert out.fsm_after.state == "IDEA"

    def test_quarantine_freezes(self) -> None:
        inputs = CanonicalSevenInputs(fragility=_Fragility(fragile=True))
        fsm = GovernanceFSM.initial()
        out = run_canonical_seven(inputs=inputs, fsm_before=fsm)
        assert out.transition.action == "QUARANTINE"
        assert out.fsm_after.state == "QUARANTINED"

    def test_demote_steps_back_one_tier(self) -> None:
        inputs = CanonicalSevenInputs(ladder=_Ladder(losing_paths=("naive",)))
        fsm = GovernanceFSM.initial().promote(target="MEASURED", evidence_supports=True, reason="m")
        out = run_canonical_seven(inputs=inputs, fsm_before=fsm)
        assert out.transition.action == "DEMOTE"
        assert out.fsm_after.state == "TESTED_ON_REAL_DATA"

    def test_stop_does_not_change_fsm_state(self) -> None:
        inputs = CanonicalSevenInputs(firewall=_Firewall(passed_all=False))
        fsm = GovernanceFSM.initial().promote(
            target="HYPOTHESIS", evidence_supports=True, reason="h"
        )
        out = run_canonical_seven(inputs=inputs, fsm_before=fsm)
        assert out.transition.action == "STOP"
        assert out.fsm_after.state == "HYPOTHESIS"

    def test_partial_inputs_supported(self) -> None:
        # Only firewall supplied — every other trigger sees None.
        inputs = CanonicalSevenInputs(firewall=_Firewall(passed_all=True))
        fsm = GovernanceFSM.initial()
        out = run_canonical_seven(inputs=inputs, fsm_before=fsm)
        assert out.transition.action == "NONE"
        assert out.fsm_after.state == "IDEA"

    def test_history_extended_by_one_per_call(self) -> None:
        fsm = GovernanceFSM.initial()
        for _ in range(3):
            out = run_canonical_seven(
                inputs=CanonicalSevenInputs(),  # all None → NONE action
                fsm_before=fsm,
            )
            fsm = out.fsm_after
        assert len(fsm.history) == 3
        assert all(r.action == "NONE" for r in fsm.history)

    def test_rejected_is_absorbing_through_orchestrator(self) -> None:
        # Drive into REJECTED, then any subsequent call cannot resurrect.
        fsm = GovernanceFSM.initial()
        out1 = run_canonical_seven(
            inputs=CanonicalSevenInputs(replication=_Replication(matched=False)),
            fsm_before=fsm,
        )
        assert out1.fsm_after.state == "REJECTED"

        # Even with all-clean inputs, REJECTED stays REJECTED.
        out2 = run_canonical_seven(
            inputs=CanonicalSevenInputs(
                firewall=_Firewall(passed_all=True),
                leakage=_Leakage(detected=False),
                ladder=_Ladder(losing_paths=()),
                fragility=_Fragility(fragile=False),
                replication=_Replication(matched=True),
            ),
            fsm_before=out1.fsm_after,
        )
        assert out2.fsm_after.state == "REJECTED"
