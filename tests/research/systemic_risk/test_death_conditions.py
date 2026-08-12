# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Hypothesis Death Engine — trigger registry + precedence tests."""

from __future__ import annotations

from dataclasses import dataclass

from research.systemic_risk.death_conditions import (
    DeathState,
    Trigger,
    default_registry,
    trigger_baseline_dominance,
    trigger_data_proxy_invalid,
    trigger_leakage_positive,
    trigger_parameter_fragility,
    trigger_replication_mismatch,
)


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


class TestIndividualTriggers:
    def test_baseline_dominance_fires_on_losing_path(self) -> None:
        out = trigger_baseline_dominance(_Ladder(losing_paths=("naive_volatility",)))
        assert out.fired
        assert out.action == "DEMOTE"

    def test_baseline_dominance_quiet_on_clean_ladder(self) -> None:
        out = trigger_baseline_dominance(_Ladder(losing_paths=tuple()))
        assert not out.fired
        assert out.action == "NONE"

    def test_baseline_dominance_quiet_when_ladder_absent(self) -> None:
        out = trigger_baseline_dominance(None)
        assert not out.fired

    def test_leakage_positive_fires(self) -> None:
        out = trigger_leakage_positive(_Leakage(detected=True))
        assert out.fired
        assert out.action == "INVALIDATE"

    def test_parameter_fragility_fires(self) -> None:
        out = trigger_parameter_fragility(_Fragility(fragile=True))
        assert out.fired
        assert out.action == "QUARANTINE"

    def test_replication_mismatch_fires(self) -> None:
        out = trigger_replication_mismatch(_Replication(matched=False))
        assert out.fired
        assert out.action == "KILL"

    def test_data_proxy_invalid_fires(self) -> None:
        out = trigger_data_proxy_invalid(_Firewall(passed_all=False))
        assert out.fired
        assert out.action == "STOP"


class TestRegistryComposition:
    def test_default_registry_has_five_triggers(self) -> None:
        reg = default_registry()
        assert len(reg.triggers) == 5
        names = {t.name for t in reg.triggers}
        assert names == {
            "T1_baseline_dominance",
            "T2_leakage_positive",
            "T3_parameter_fragility",
            "T4_replication_mismatch",
            "T5_data_proxy_invalid",
        }

    def test_no_trigger_fired_yields_none(self) -> None:
        reg = default_registry()
        state = DeathState(
            ladder=_Ladder(losing_paths=tuple()),
            leakage=_Leakage(detected=False),
            fragility=_Fragility(fragile=False),
            replication=_Replication(matched=True),
            firewall=_Firewall(passed_all=True),
        )
        out = reg.evaluate(state)
        assert out.action == "NONE"
        assert out.fired_triggers == ()

    def test_kill_dominates_demote_simultaneously_fired(self) -> None:
        # T1 (DEMOTE) AND T4 (KILL) both fire — KILL must win.
        reg = default_registry()
        state = DeathState(
            ladder=_Ladder(losing_paths=("naive",)),
            replication=_Replication(matched=False),
        )
        out = reg.evaluate(state)
        assert out.action == "KILL"
        assert "T1_baseline_dominance" in out.fired_triggers
        assert "T4_replication_mismatch" in out.fired_triggers

    def test_invalidate_dominates_quarantine(self) -> None:
        reg = default_registry()
        state = DeathState(
            leakage=_Leakage(detected=True),
            fragility=_Fragility(fragile=True),
        )
        out = reg.evaluate(state)
        assert out.action == "INVALIDATE"

    def test_quarantine_dominates_demote(self) -> None:
        reg = default_registry()
        state = DeathState(
            ladder=_Ladder(losing_paths=("x",)),
            fragility=_Fragility(fragile=True),
        )
        out = reg.evaluate(state)
        assert out.action == "QUARANTINE"

    def test_demote_dominates_stop(self) -> None:
        reg = default_registry()
        state = DeathState(
            ladder=_Ladder(losing_paths=("x",)),
            firewall=_Firewall(passed_all=False),
        )
        out = reg.evaluate(state)
        assert out.action == "DEMOTE"

    def test_extend_returns_new_registry(self) -> None:
        reg = default_registry()
        extended = reg.extend(
            Trigger(
                name="custom",
                action_when_fired="STOP",
                evaluate=lambda s: trigger_data_proxy_invalid(s.firewall),
            )
        )
        assert len(reg.triggers) == 5
        assert len(extended.triggers) == 6
