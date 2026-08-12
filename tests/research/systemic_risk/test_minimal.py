# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Minimal Canonical Seven — single-file front-door tests."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from research.systemic_risk.minimal import (
    DEMOTE,
    INVALIDATE,
    KILL,
    NONE,
    QUARANTINE,
    QUARANTINED,
    REJECTED,
    STOP,
    Claim,
    TierAction,
    auc_bf,
    evaluate,
    firewall,
    initial_claim,
    leakage,
    replication_bf,
    rerun,
    state_name,
)

_lattice = st.sampled_from(list(TierAction))


class TestActionLattice:
    def test_strict_order(self) -> None:
        assert NONE < STOP < DEMOTE < QUARANTINE < INVALIDATE < KILL

    @given(actions=st.lists(_lattice, min_size=1, max_size=8))
    def test_max_is_join(self, actions: list[TierAction]) -> None:
        assert max(actions) == max(actions, key=int)


class TestInitialClaim:
    def test_default_prior(self) -> None:
        c = initial_claim("C-1")
        assert c.tier == 0
        assert c.posterior_log_odds == -1.0
        assert c.evidence_count == 0
        assert c.last_action == NONE

    def test_custom_prior(self) -> None:
        c = initial_claim("C-1", prior_log_odds=0.5)
        assert c.posterior_log_odds == 0.5


class TestStateName:
    def test_ladder_states(self) -> None:
        assert state_name(0) == "IDEA"
        assert state_name(7) == "VALIDATED"

    def test_quarantined(self) -> None:
        assert state_name(QUARANTINED) == "QUARANTINED"

    def test_rejected(self) -> None:
        assert state_name(REJECTED) == "REJECTED"

    def test_unknown_tier_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown tier"):
            state_name(99)


class TestBayesFactors:
    def test_auc_half_lindley_penalty(self) -> None:
        # AUC=0.5 → BF < 1 (Lindley penalty under non-trivial n_eff).
        assert auc_bf(0.5, n_pos=10, n_neg=10) < 1.0

    def test_auc_above_half_favours(self) -> None:
        assert auc_bf(0.85, n_pos=20, n_neg=20) > 1.0

    def test_auc_invalid_rejected(self) -> None:
        with pytest.raises(ValueError, match="auc"):
            auc_bf(1.5, n_pos=10, n_neg=10)

    def test_replication_match_strong(self) -> None:
        assert replication_bf(True) == 100.0

    def test_replication_mismatch_zero(self) -> None:
        assert replication_bf(False) == 0.0


class TestFirewall:
    def _good(self) -> dict[date, np.ndarray]:
        m = np.array(
            [[0.0, 1.0, 2.0], [3.0, 0.0, 4.0], [5.0, 6.0, 0.0]],
            dtype=np.float64,
        )
        base = date(2026, 5, 1)
        return {base + timedelta(days=i): m.copy() for i in range(3)}

    def test_clean_passes(self) -> None:
        passed, reason = firewall(self._good(), n_nodes=3)
        assert passed
        assert "8 gates" in reason

    def test_empty_panel_rejects(self) -> None:
        passed, reason = firewall({}, n_nodes=3)
        assert not passed
        assert "empty" in reason

    def test_nan_rejects(self) -> None:
        panels = self._good()
        d = next(iter(panels))
        panels[d][0, 1] = np.nan
        passed, reason = firewall(panels, n_nodes=3)
        assert not passed
        assert "G3" in reason

    def test_negative_rejects(self) -> None:
        panels = self._good()
        d = next(iter(panels))
        panels[d][0, 1] = -1.0
        passed, reason = firewall(panels, n_nodes=3)
        assert not passed
        assert "G4" in reason

    def test_self_loop_rejects(self) -> None:
        panels = self._good()
        d = next(iter(panels))
        panels[d][0, 0] = 1.0
        passed, reason = firewall(panels, n_nodes=3)
        assert not passed
        assert "G5" in reason

    def test_all_zero_rejects(self) -> None:
        panels = {date(2026, 5, 1): np.zeros((3, 3), dtype=np.float64)}
        passed, reason = firewall(panels, n_nodes=3)
        assert not passed
        assert "G6" in reason


class TestLeakage:
    def test_clean_passes(self) -> None:
        detected, _ = leakage()
        assert not detected

    def test_centered_window_caught(self) -> None:
        detected, reason = leakage(config={"center": True})
        assert detected
        assert "S3" in reason

    def test_full_sample_zscore_caught(self) -> None:
        detected, reason = leakage(op_log=["full_sample_zscore"])
        assert detected
        assert "S4" in reason

    def test_label_leakage_caught(self) -> None:
        detected, reason = leakage(op_graph=[("future_join", 20, 10)])
        assert detected
        assert "S5" in reason

    def test_post_event_caught(self) -> None:
        detected, reason = leakage(min_lead_time=0)
        assert detected
        assert "S2" in reason

    def test_crisis_tuning_caught(self) -> None:
        detected, _ = leakage(
            crisis_lock_utc="2026-05-08T12:00:00+00:00",
            first_eval_utc="2026-05-01T12:00:00+00:00",
        )
        assert detected


class TestRerun:
    def test_match(self) -> None:
        matched, _ = rerun(
            primary_metric=0.85,
            secondary_metric=0.85,
            primary_seed=42,
            secondary_seed=42,
            primary_config_hash="a" * 64,
            secondary_config_hash="a" * 64,
        )
        assert matched

    def test_seed_diverged(self) -> None:
        matched, reason = rerun(
            primary_metric=0.85,
            secondary_metric=0.85,
            primary_seed=1,
            secondary_seed=2,
            primary_config_hash="a" * 64,
            secondary_config_hash="a" * 64,
        )
        assert not matched
        assert reason == "seed_diverged"

    def test_metric_deviation(self) -> None:
        matched, reason = rerun(
            primary_metric=0.85,
            secondary_metric=0.86,
            primary_seed=42,
            secondary_seed=42,
            primary_config_hash="a" * 64,
            secondary_config_hash="a" * 64,
        )
        assert not matched
        assert reason == "metric_deviation_exceeds_tolerance"

    def test_nan_metric_caught(self) -> None:
        matched, reason = rerun(
            primary_metric=math.nan,
            secondary_metric=0.85,
            primary_seed=42,
            secondary_seed=42,
            primary_config_hash="a" * 64,
            secondary_config_hash="a" * 64,
        )
        assert not matched
        assert "non_finite" in reason


class TestEvaluate:
    def test_clean_round(self) -> None:
        c0 = initial_claim("C-1")
        c1 = evaluate(
            c0,
            losing_paths=(),
            leakage_detected=False,
            fragile=False,
            replication_matched=True,
            firewall_passed_all=True,
        )
        assert c1.last_action == NONE
        assert c1.tier == 0

    def test_kill_path(self) -> None:
        c0 = initial_claim("C-1")
        c1 = evaluate(c0, replication_matched=False)
        assert c1.last_action == KILL
        assert c1.tier == REJECTED

    def test_kill_dominates_demote(self) -> None:
        c0 = initial_claim("C-1")
        c1 = evaluate(
            c0,
            losing_paths=("naive",),
            replication_matched=False,
        )
        assert c1.last_action == KILL
        assert c1.tier == REJECTED

    def test_invalidate_resets_to_idea(self) -> None:
        c0 = Claim("C-1", tier=5, posterior_log_odds=2.0, evidence_count=3, last_action=NONE)
        c1 = evaluate(c0, leakage_detected=True)
        assert c1.last_action == INVALIDATE
        assert c1.tier == 0

    def test_quarantine(self) -> None:
        c0 = initial_claim("C-1")
        c1 = evaluate(c0, fragile=True)
        assert c1.last_action == QUARANTINE
        assert c1.tier == QUARANTINED

    def test_demote(self) -> None:
        c0 = Claim("C-1", tier=5, posterior_log_odds=0.0, evidence_count=0, last_action=NONE)
        c1 = evaluate(c0, losing_paths=("p1",))
        assert c1.last_action == DEMOTE
        assert c1.tier == 4

    def test_demote_clamps_at_idea(self) -> None:
        c0 = initial_claim("C-1")  # tier 0
        c1 = evaluate(c0, losing_paths=("p1",))
        assert c1.tier == 0  # cannot demote below IDEA

    def test_stop_does_not_change_tier(self) -> None:
        c0 = Claim("C-1", tier=3, posterior_log_odds=0.0, evidence_count=0, last_action=NONE)
        c1 = evaluate(c0, firewall_passed_all=False)
        assert c1.last_action == STOP
        assert c1.tier == 3

    def test_evidence_updates_posterior(self) -> None:
        c0 = initial_claim("C-1", prior_log_odds=0.0)
        c1 = evaluate(c0, new_evidence_log_bf=2.0)
        assert c1.posterior_log_odds == pytest.approx(2.0)
        assert c1.evidence_count == 1

    def test_posterior_floor_drives_kill(self) -> None:
        c0 = initial_claim("C-1", prior_log_odds=0.0)
        # 3 disfavouring evidences of -2 each → posterior -6 ≤ -5 → KILL
        c = c0
        for _ in range(3):
            c = evaluate(c, new_evidence_log_bf=-2.0)
        assert c.tier == REJECTED
        assert c.last_action == KILL

    def test_rejected_is_absorbing(self) -> None:
        c0 = initial_claim("C-1")
        killed = evaluate(c0, replication_matched=False)
        assert killed.tier == REJECTED
        # Any subsequent call cannot resurrect.
        for action_kw in [
            {"replication_matched": True},
            {"firewall_passed_all": True},
            {"leakage_detected": False},
            {"new_evidence_log_bf": 100.0},
        ]:
            after = evaluate(killed, **action_kw)  # type: ignore[arg-type]
            assert after.tier == REJECTED
            assert after.last_action == NONE

    def test_invalid_evidence_bf_rejected(self) -> None:
        c0 = initial_claim("C-1")
        with pytest.raises(ValueError, match="finite"):
            evaluate(c0, new_evidence_log_bf=math.nan)

    def test_immutability(self) -> None:
        c0 = initial_claim("C-1")
        c1 = evaluate(c0, replication_matched=False)
        # NamedTuple is immutable by construction.
        assert c0.tier == 0
        assert c1.tier == REJECTED
        assert c0 is not c1


class TestPropertyBased:
    @given(st.integers(min_value=0, max_value=7))
    def test_demote_decreases_or_clamps(self, tier: int) -> None:
        c0 = Claim("C", tier=tier, posterior_log_odds=0.0, evidence_count=0, last_action=NONE)
        c1 = evaluate(c0, losing_paths=("p",))
        assert c1.tier == max(0, tier - 1)

    @given(st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False))
    def test_evidence_accumulates_additively(self, bf_log: float) -> None:
        c0 = initial_claim("C", prior_log_odds=0.0)
        c1 = evaluate(c0, new_evidence_log_bf=bf_log)
        if c1.tier != REJECTED:
            assert c1.posterior_log_odds == pytest.approx(bf_log)
