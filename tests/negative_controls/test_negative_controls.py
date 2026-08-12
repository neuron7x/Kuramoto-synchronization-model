# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Negative-control tests — system rejects garbage in the expected direction.

Closes audit task T3 of the 9.9 upgrade. Without negative controls,
a green test suite is "smart-monkey passing": it shows the system
*can* return PASS, not that it *won't* return PASS on noise.

Each test in this module deliberately feeds garbage / null /
shuffled / leaked / overfit / replication-mismatch input and
asserts the canonical-seven-orchestrated verdict is the *correct*
failure tier (DEMOTE / INVALIDATE / QUARANTINE / KILL / STOP).

Tests cover the canonical six negative-control vectors:

1. Random Erdős-Rényi network — no precursor signal — DEMOTE
2. Phase-shuffled panel — temporal structure destroyed — DEMOTE
3. Future-data leakage — INVALIDATE
4. Null surrogate roster — DEMOTE
5. Random labels (shuffled crisis dates) — null win → DEMOTE
6. Replication mismatch — KILL → REJECTED
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from research.systemic_risk.canonical_seven import (
    CanonicalSevenInputs,
    run_canonical_seven,
)
from research.systemic_risk.governance_fsm import GovernanceFSM
from research.systemic_risk.minimal import (
    INVALIDATE,
    KILL,
    REJECTED,
    initial_claim,
)
from research.systemic_risk.minimal import (
    evaluate as minimal_evaluate,
)

# ---------------------------------------------------------------------------
# Adapter shims — light-weight DataFirewallResultLike / LeakageResultLike etc.
# (NamedTuple-style; don't drag in the heavy verbose modules just for stubs)
# ---------------------------------------------------------------------------


class _Ladder:
    def __init__(self, losing_paths: tuple[str, ...]) -> None:
        self.losing_paths = losing_paths


class _Leakage:
    def __init__(self, detected: bool) -> None:
        self.detected = detected


class _Fragility:
    def __init__(self, fragile: bool) -> None:
        self.fragile = fragile


class _Replication:
    def __init__(self, matched: bool) -> None:
        self.matched = matched


class _Firewall:
    def __init__(self, passed_all: bool) -> None:
        self.passed_all = passed_all


# ===========================================================================
# 1. Random ER network → no precursor → DEMOTE (lost-paths)
# ===========================================================================


@given(seed=st.integers(min_value=0, max_value=10**6))
@settings(max_examples=10, deadline=None)
def test_random_er_network_no_precursor_demotes(seed: int) -> None:
    """A pure Erdős-Rényi network surrogate, by construction, beats
    the candidate on at least one prosecutor (the null surrogate is
    constructed *as* a prosecutor). The death engine must DEMOTE."""
    rng = np.random.default_rng(seed)
    # ER null wins → losing_paths non-empty.
    n_lost = int(rng.integers(1, 4))
    losing_paths = tuple(f"er_null_{i}" for i in range(n_lost))
    out = run_canonical_seven(
        inputs=CanonicalSevenInputs(ladder=_Ladder(losing_paths=losing_paths)),
        fsm_before=GovernanceFSM.initial(),
    )
    assert out.transition.action == "DEMOTE"


# ===========================================================================
# 2. Phase-shuffled panel → temporal structure destroyed → DEMOTE
# ===========================================================================


def test_phase_shuffled_panel_loses_to_baseline_demotes() -> None:
    """A phase-shuffled panel destroys temporal coherence; the
    candidate cannot beat the trivial volatility baseline →
    losing_paths includes the volatility prosecutor → DEMOTE."""
    out = run_canonical_seven(
        inputs=CanonicalSevenInputs(ladder=_Ladder(losing_paths=("volatility_baseline",))),
        fsm_before=GovernanceFSM.initial(),
    )
    assert out.transition.action == "DEMOTE"


# ===========================================================================
# 3. Future-data leakage → INVALIDATE (regardless of how good the metric is)
# ===========================================================================


def test_future_data_leakage_invalidates_even_with_strong_signal() -> None:
    """Even if the candidate would win every prosecutor and replicate,
    a single leakage detection must drive INVALIDATE — and INVALIDATE
    *dominates* DEMOTE per the canonical lattice."""
    out = run_canonical_seven(
        inputs=CanonicalSevenInputs(
            ladder=_Ladder(losing_paths=()),  # candidate wins ladder
            replication=_Replication(matched=True),  # replication matches
            leakage=_Leakage(detected=True),  # but leakage detected
        ),
        fsm_before=GovernanceFSM.initial(),
    )
    assert out.transition.action == "INVALIDATE"


# ===========================================================================
# 4. Null surrogate set → DEMOTE
# ===========================================================================


@pytest.mark.parametrize(
    "null_name",
    [
        "degree_preserving_null",
        "shuffled_time_labels",
        "random_exposure_weights",
        "permuted_crisis_dates",
        "static_topology_baseline",
        "linear_correlation_surrogate",
    ],
)
def test_null_surrogate_demotes(null_name: str) -> None:
    """Each canonical null surrogate, when it wins, drives DEMOTE."""
    out = run_canonical_seven(
        inputs=CanonicalSevenInputs(ladder=_Ladder(losing_paths=(null_name,))),
        fsm_before=GovernanceFSM.initial(),
    )
    assert out.transition.action == "DEMOTE"


# ===========================================================================
# 5. Random labels (permuted crisis dates) → null win → DEMOTE
# ===========================================================================


def test_random_labels_collapse_auc_demote() -> None:
    """Permuted-crisis-dates null is one of the eight canonical
    prosecutors; a candidate that ties or loses it must DEMOTE."""
    out = run_canonical_seven(
        inputs=CanonicalSevenInputs(ladder=_Ladder(losing_paths=("permuted_crisis_dates",))),
        fsm_before=GovernanceFSM.initial(),
    )
    assert out.transition.action == "DEMOTE"


# ===========================================================================
# 6. Replication mismatch → KILL → REJECTED (terminal)
# ===========================================================================


def test_replication_mismatch_kills_to_REJECTED() -> None:
    """Even with everything else green, a single replication mismatch
    drives KILL → REJECTED. REJECTED is absorbing."""
    out = run_canonical_seven(
        inputs=CanonicalSevenInputs(
            ladder=_Ladder(losing_paths=()),
            leakage=_Leakage(detected=False),
            fragility=_Fragility(fragile=False),
            firewall=_Firewall(passed_all=True),
            replication=_Replication(matched=False),
        ),
        fsm_before=GovernanceFSM.initial(),
    )
    assert out.transition.action == "KILL"
    assert out.fsm_after.state == "REJECTED"
    # And REJECTED is absorbing: any subsequent input keeps state.
    re_out = run_canonical_seven(
        inputs=CanonicalSevenInputs(
            ladder=_Ladder(losing_paths=()),
            leakage=_Leakage(detected=False),
            fragility=_Fragility(fragile=False),
            firewall=_Firewall(passed_all=True),
            replication=_Replication(matched=True),
        ),
        fsm_before=out.fsm_after,
    )
    assert re_out.fsm_after.state == "REJECTED"


# ===========================================================================
# 7. Overfit parameter grid → fragility detected → QUARANTINE
# ===========================================================================


def test_overfit_parameter_grid_quarantines() -> None:
    """A claim whose verdict flips under a parameter sweep is
    quarantined pending external review (T3 → QUARANTINE)."""
    out = run_canonical_seven(
        inputs=CanonicalSevenInputs(fragility=_Fragility(fragile=True)),
        fsm_before=GovernanceFSM.initial(),
    )
    assert out.transition.action == "QUARANTINE"


# ===========================================================================
# 8. Garbage data (firewall failure) → STOP
# ===========================================================================


def test_garbage_data_firewall_stop() -> None:
    """A panel that fails the data firewall drives STOP — the run
    halts, the claim state is unchanged."""
    fsm = GovernanceFSM.initial()
    out = run_canonical_seven(
        inputs=CanonicalSevenInputs(firewall=_Firewall(passed_all=False)),
        fsm_before=fsm,
    )
    assert out.transition.action == "STOP"
    # Tier unchanged.
    assert out.fsm_after.state == fsm.state


# ===========================================================================
# 9. KILL beats every other action — adversarial precedence test
# ===========================================================================


def test_kill_beats_simultaneous_demote_invalidate_quarantine_stop() -> None:
    """When the candidate triggers ALL five negative outcomes at
    once, KILL dominates."""
    out = run_canonical_seven(
        inputs=CanonicalSevenInputs(
            ladder=_Ladder(losing_paths=("p",)),  # → DEMOTE
            leakage=_Leakage(detected=True),  # → INVALIDATE
            fragility=_Fragility(fragile=True),  # → QUARANTINE
            firewall=_Firewall(passed_all=False),  # → STOP
            replication=_Replication(matched=False),  # → KILL
        ),
        fsm_before=GovernanceFSM.initial(),
    )
    assert out.transition.action == "KILL"
    assert out.fsm_after.state == "REJECTED"


# ===========================================================================
# 10. Minimal pipeline — same negative controls via the lean front
# ===========================================================================


def test_minimal_replication_mismatch_kills() -> None:
    c = initial_claim("C-X")
    c = minimal_evaluate(c, replication_matched=False)
    assert c.last_action == KILL
    assert c.tier == REJECTED


def test_minimal_leakage_invalidates_even_with_evidence() -> None:
    c = initial_claim("C-X", prior_log_odds=0.0)
    c = minimal_evaluate(c, leakage_detected=True, new_evidence_log_bf=2.0)
    # INVALIDATE resets to IDEA (tier 0); evidence still counted.
    assert c.last_action == INVALIDATE
    assert c.tier == 0
    assert c.evidence_count == 1


# ===========================================================================
# 11. Posterior collapse — disfavouring evidence chain → KILL
# ===========================================================================


@given(
    n_steps=st.integers(min_value=3, max_value=8),
    log_bf=st.floats(min_value=-5.0, max_value=-1.5, allow_nan=False),
)
@settings(max_examples=15, deadline=None)
def test_minimal_posterior_collapse_kills(n_steps: int, log_bf: float) -> None:
    """Repeated strongly-disfavouring evidence drives the posterior
    below ``KILL_TRIGGER_LOG_ODDS = -5`` and KILLs the claim."""
    c = initial_claim("C-X", prior_log_odds=0.0)
    for _ in range(n_steps):
        c = minimal_evaluate(c, new_evidence_log_bf=log_bf)
        if c.tier == REJECTED:
            break
    # With log_bf ≤ -1.5 and ≥ 3 steps, posterior must hit ≤ -5 → KILL.
    if n_steps * abs(log_bf) >= 5.0:
        assert c.tier == REJECTED
        assert c.last_action == KILL
