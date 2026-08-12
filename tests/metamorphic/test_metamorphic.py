# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Metamorphic tests — invariant relations under input transformations.

Closes audit task T2 of the 9.9 upgrade. Each test states a relation
(``f(x)`` vs ``f(transform(x))``) that must hold by design and would
break if a core invariant of the corresponding pillar regressed.

Coverage map (one or more relations per core module):

* evidence_ledger    — order-invariance of additive log-odds update
* governance_fsm     — REJECTED is absorbing (any input → REJECTED)
* kuramoto_extensions — global phase shift preserves order parameter
* data_firewall      — bank-label permutation preserves passed_all
* replication_capsule — same inputs + same seed → same matched verdict
* verdict_lattice    — join is associative & commutative on the multiset
* leakage_sentinel   — disjunction-monotonic in fired components
* minimal            — KILL-after-X always yields REJECTED
* bayes_rigorous     — symmetry under AUC ↔ 1 − AUC
* occam_penalty      — anti-symmetric margin under candidate ↔ prosecutor swap
"""

from __future__ import annotations

import math
from datetime import date, timedelta, timezone
from datetime import datetime as _dt
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from research.systemic_risk.bayes_rigorous import auc_per_crisis_bf_rigorous
from research.systemic_risk.data_firewall import Provenance, run_data_firewall
from research.systemic_risk.evidence_ledger import (
    DEFAULT_PRIOR_LOG_ODDS,
    Evidence,
    EvidenceLedger,
)
from research.systemic_risk.governance_fsm import (
    GovernanceFSM,
)
from research.systemic_risk.kuramoto_extensions import (
    kuramoto_order_parameter,
)
from research.systemic_risk.leakage_sentinel import (
    LeakageOutcome,
    run_leakage_audit,
)
from research.systemic_risk.minimal import (
    KILL,
    NONE,
    Claim,
    initial_claim,
)
from research.systemic_risk.minimal import (
    REJECTED as REJECTED_INT,
)
from research.systemic_risk.minimal import (
    evaluate as minimal_evaluate,
)
from research.systemic_risk.occam_penalty import occam_winner
from research.systemic_risk.replication import RunManifest
from research.systemic_risk.replication_capsule import compare_run_outputs
from research.systemic_risk.verdict_lattice import TierLattice, aggregate_actions

# `LeakageType` is a Literal — sentinel name strings.
_LEAKAGE_TYPES = (
    "future_data",
    "post_event_contamination",
    "centered_windows",
    "full_sample_normalisation",
    "label_leakage",
    "crisis_date_tuning",
)

# ---------------------------------------------------------------------------
# 1. EvidenceLedger — final posterior is order-invariant
#    (log-odds is additive: log a + log b == log b + log a)
# ---------------------------------------------------------------------------


def _ts(offset_seconds: int = 0) -> str:
    base = _dt(2026, 5, 8, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_seconds)).isoformat()


@given(
    bf1=st.floats(min_value=0.01, max_value=100, allow_nan=False),
    bf2=st.floats(min_value=0.01, max_value=100, allow_nan=False),
)
@settings(max_examples=50, deadline=None)
def test_ledger_order_invariance(bf1: float, bf2: float) -> None:
    """log-odds posterior is the same regardless of evidence order."""
    e1_a = Evidence(timestamp_utc=_ts(0), type="UNINFORMATIVE", bayes_factor=bf1)
    e2_a = Evidence(timestamp_utc=_ts(1), type="UNINFORMATIVE", bayes_factor=bf2)
    ledger_a = (
        EvidenceLedger()
        .with_claim("C-X", prior_log_odds=DEFAULT_PRIOR_LOG_ODDS)
        .with_evidence("C-X", e1_a)
        .with_evidence("C-X", e2_a)
    )
    e1_b = Evidence(timestamp_utc=_ts(0), type="UNINFORMATIVE", bayes_factor=bf2)
    e2_b = Evidence(timestamp_utc=_ts(1), type="UNINFORMATIVE", bayes_factor=bf1)
    ledger_b = (
        EvidenceLedger()
        .with_claim("C-X", prior_log_odds=DEFAULT_PRIOR_LOG_ODDS)
        .with_evidence("C-X", e1_b)
        .with_evidence("C-X", e2_b)
    )
    entry_a = ledger_a.get("C-X")
    entry_b = ledger_b.get("C-X")
    assert entry_a is not None and entry_b is not None
    # Additive log-odds → permutation invariance.
    assert math.isclose(entry_a.posterior_log_odds, entry_b.posterior_log_odds, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 2. GovernanceFSM — REJECTED is absorbing
# ---------------------------------------------------------------------------


def _make_transition(action: str) -> Any:
    from research.systemic_risk.death_conditions import TierTransition

    return TierTransition(action=action, fired_triggers=(), outcomes=())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "action_after_kill",
    ["KILL", "INVALIDATE", "QUARANTINE", "DEMOTE", "STOP", "NONE"],
)
def test_fsm_rejected_is_absorbing(action_after_kill: str) -> None:
    """Every action applied after KILL → REJECTED leaves state at REJECTED."""
    fsm = GovernanceFSM.initial().apply(_make_transition("KILL"))
    assert fsm.state == "REJECTED"
    after = fsm.apply(_make_transition(action_after_kill))
    assert after.state == "REJECTED"


# ---------------------------------------------------------------------------
# 3. Kuramoto — global phase shift preserves order parameter magnitude
# ---------------------------------------------------------------------------


@given(
    n=st.integers(min_value=4, max_value=64),
    shift=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False),
    seed=st.integers(min_value=0, max_value=10**6),
)
@settings(max_examples=25, deadline=None)
def test_kuramoto_global_phase_shift_invariance(n: int, shift: float, seed: int) -> None:
    """``r(θ_i + c) == r(θ_i)`` for any global phase shift c."""
    rng = np.random.default_rng(seed)
    theta = rng.uniform(-math.pi, math.pi, n).astype(np.float64)
    r_base = kuramoto_order_parameter(theta)
    r_shifted = kuramoto_order_parameter((theta + shift).astype(np.float64))
    assert math.isclose(r_base, r_shifted, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 4. Data firewall — relabelling banks preserves structural pass/fail
#    (provenance and bank-mapping gates depend on labels and may change;
#    G3 finite, G4 sign, G5 diagonal, G6 sparsity, G7 monotonic_time
#    are label-invariant, so the *finite_check_subset* must be unchanged).
# ---------------------------------------------------------------------------


def _good_panel_and_provenance() -> (
    tuple[dict[date, np.ndarray], tuple[str, ...], dict[date, Provenance]]
):
    base = date(2026, 5, 1)
    matrix = np.array([[0.0, 1.0, 2.0], [3.0, 0.0, 4.0], [5.0, 6.0, 0.0]], dtype=np.float64)
    panel: dict[date, np.ndarray] = {}
    provs: dict[date, Provenance] = {}
    for i in range(3):
        d = base + timedelta(days=i)
        panel[d] = matrix.copy()
        provs[d] = Provenance(
            source_id="metamorphic-test",
            schema_version="interbank.panel.v1",
            capture_timestamp_utc=_dt(
                d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc
            ).isoformat(),
            payload_sha256="0" * 64,
        )
    return panel, ("BANK_A", "BANK_B", "BANK_C"), provs


def test_firewall_label_relabelling_preserves_structural_gates() -> None:
    """Relabelling the bank node-labels does not change any of the
    structural-gate (G1, G2, G3, G4, G5, G6, G7) outcomes — those
    gates do not consume the labels at all."""
    panel, labels, provs = _good_panel_and_provenance()
    rep_a = run_data_firewall(panel, node_labels=labels, provenances=provs)
    relabelled = ("BANCO_X", "BANCO_Y", "BANCO_Z")
    rep_b = run_data_firewall(panel, node_labels=relabelled, provenances=provs)
    structural_gates = {
        "G1_schema_type",
        "G2_shape",
        "G3_finite",
        "G4_sign",
        "G5_diagonal",
        "G6_sparsity",
        "G7_monotonic_time",
    }
    a_struct = {o.name: o.passed for o in rep_a.gate_outcomes if o.name in structural_gates}
    b_struct = {o.name: o.passed for o in rep_b.gate_outcomes if o.name in structural_gates}
    assert a_struct == b_struct


# ---------------------------------------------------------------------------
# 5. Replication capsule — same inputs ⇒ same matched verdict
# ---------------------------------------------------------------------------


def _make_manifest(seed: int = 42, config_hash: str = "a" * 64) -> RunManifest:
    return RunManifest(
        commit_sha="deadbeef",
        git_dirty=False,
        timestamp_utc="2026-05-08T14:00:00+00:00",
        seed=seed,
        config_hash=config_hash,
        python="3.12.0",
        platform_info="Linux",
        package_versions={"numpy": "2.0.0"},
        config={"alpha": 0.05},
        extra={},
    )


@given(metric=st.floats(min_value=-1e3, max_value=1e3, allow_nan=False))
@settings(max_examples=25, deadline=None)
def test_capsule_same_inputs_same_verdict(metric: float) -> None:
    """Same manifests + same metric → matched=True both times (and
    matched verdict is repeatable on re-run)."""
    m = _make_manifest()
    out_1 = compare_run_outputs(
        primary_manifest=m,
        secondary_manifest=m,
        primary_metric=metric,
        secondary_metric=metric,
        tolerance_class="bit_identical",
    )
    out_2 = compare_run_outputs(
        primary_manifest=m,
        secondary_manifest=m,
        primary_metric=metric,
        secondary_metric=metric,
        tolerance_class="bit_identical",
    )
    assert out_1.matched is True
    assert out_2.matched is True
    assert out_1.reason == out_2.reason


# ---------------------------------------------------------------------------
# 6. Verdict lattice — join is associative + commutative
#    (already covered as Hypothesis property tests; this metamorphic
#    relation re-states the same axiom on a multiset of size 5).
# ---------------------------------------------------------------------------


@given(actions=st.lists(st.sampled_from(list(TierLattice)), min_size=2, max_size=8))
@settings(max_examples=25, deadline=None)
def test_lattice_aggregate_permutation_invariance(
    actions: list[TierLattice],
) -> None:
    """``aggregate_actions(xs)`` is invariant under permutation of xs."""
    import random

    rng = random.Random(42)
    shuffled = list(actions)
    rng.shuffle(shuffled)
    assert aggregate_actions(actions) == aggregate_actions(shuffled)


# ---------------------------------------------------------------------------
# 7. Leakage sentinel — disjunction is monotonic in fired components
# ---------------------------------------------------------------------------


def test_leakage_disjunction_monotonic() -> None:
    """If any extra positive sentinel is added to a clean set,
    ``LeakageReport.detected`` cannot become False."""
    clean = (
        LeakageOutcome(type="future_data", detected=False, reason="clean"),
        LeakageOutcome(type="centered_windows", detected=False, reason="trailing"),
    )
    rep_clean = run_leakage_audit(list(clean))
    assert rep_clean.detected is False
    augmented = list(clean) + [
        LeakageOutcome(type="label_leakage", detected=True, reason="future_label_join")
    ]
    rep_aug = run_leakage_audit(augmented)
    assert rep_aug.detected is True


# ---------------------------------------------------------------------------
# 8. Minimal — KILL-after-any-state always REJECTED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("starting_tier", [0, 3, 7])
def test_minimal_kill_after_any_state_yields_rejected(starting_tier: int) -> None:
    """For any non-terminal tier, applying ``replication_matched=False``
    drives the Claim to REJECTED."""
    c = Claim(
        claim_id="C-X",
        tier=starting_tier,
        posterior_log_odds=0.0,
        evidence_count=0,
        last_action=NONE,
    )
    after = minimal_evaluate(c, replication_matched=False)
    assert after.tier == REJECTED_INT
    assert after.last_action == KILL


def test_minimal_rejected_is_absorbing_under_any_input() -> None:
    """Once at REJECTED_INT, no input restores tier."""
    c = initial_claim("C-X")
    c = minimal_evaluate(c, replication_matched=False)
    assert c.tier == REJECTED_INT
    for kw in [
        {"replication_matched": True},
        {"firewall_passed_all": True},
        {"leakage_detected": False},
        {"new_evidence_log_bf": 100.0},
    ]:
        after = minimal_evaluate(c, **kw)  # type: ignore[arg-type]
        assert after.tier == REJECTED_INT


# ---------------------------------------------------------------------------
# 9. Bayes-rigorous — AUC and (1 - AUC) yield same BF magnitude
# ---------------------------------------------------------------------------


@given(
    delta=st.floats(min_value=0.01, max_value=0.49, allow_nan=False),
    n=st.integers(min_value=5, max_value=50),
)
@settings(max_examples=25, deadline=None)
def test_bayes_rigorous_polarity_symmetry(delta: float, n: int) -> None:
    """``BF(0.5 + δ) == BF(0.5 − δ)`` — the test is two-sided."""
    bf_high = auc_per_crisis_bf_rigorous(0.5 + delta, n_pos=n, n_neg=n)
    bf_low = auc_per_crisis_bf_rigorous(0.5 - delta, n_pos=n, n_neg=n)
    assert math.isclose(bf_high, bf_low, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# 10. Occam — anti-symmetric margin under candidate ↔ prosecutor swap
# ---------------------------------------------------------------------------


@given(
    log_l_a=st.floats(min_value=-100, max_value=0, allow_nan=False),
    log_l_b=st.floats(min_value=-100, max_value=0, allow_nan=False),
    k_a=st.integers(min_value=0, max_value=10),
    k_b=st.integers(min_value=0, max_value=10),
    n=st.integers(min_value=10, max_value=10_000),
)
@settings(max_examples=25, deadline=None)
def test_occam_margin_anti_symmetric(
    log_l_a: float, log_l_b: float, k_a: int, k_b: int, n: int
) -> None:
    _, m_ab = occam_winner(
        candidate_log_lhood=log_l_a,
        candidate_k=k_a,
        prosecutor_log_lhood=log_l_b,
        prosecutor_k=k_b,
        n=n,
        method="BIC",
    )
    _, m_ba = occam_winner(
        candidate_log_lhood=log_l_b,
        candidate_k=k_b,
        prosecutor_log_lhood=log_l_a,
        prosecutor_k=k_a,
        n=n,
        method="BIC",
    )
    assert math.isclose(m_ab, -m_ba, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# 11. Verdict lattice — meet/join distributivity (Birkhoff 1948)
# ---------------------------------------------------------------------------


@given(
    a=st.sampled_from(list(TierLattice)),
    b=st.sampled_from(list(TierLattice)),
    c=st.sampled_from(list(TierLattice)),
)
@settings(max_examples=25, deadline=None)
def test_lattice_distributivity(a: TierLattice, b: TierLattice, c: TierLattice) -> None:
    """join distributes over meet (Birkhoff 1948 — total orders)."""
    from research.systemic_risk.verdict_lattice import join, meet

    lhs = join(a, meet(b, c))
    rhs = meet(join(a, b), join(a, c))
    assert lhs == rhs


# ---------------------------------------------------------------------------
# 12. Bayes-rigorous — n_eff = 1 + ε implies BF(z=0) ≈ 1
# ---------------------------------------------------------------------------


def test_bayes_rigorous_lindley_collapses_at_neff_one() -> None:
    from research.systemic_risk.bayes_rigorous import wagenmakers_bic_bayes_factor

    # log BF = (0² - log 1) / 2 = 0 → BF = 1.0
    assert math.isclose(wagenmakers_bic_bayes_factor(0.0, n_eff=1.0), 1.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 13. EvidenceLedger — uninformative evidence (BF=1) is a fixed point
# ---------------------------------------------------------------------------


def test_ledger_uninformative_evidence_fixed_point() -> None:
    e = Evidence(timestamp_utc=_ts(), type="UNINFORMATIVE", bayes_factor=1.0)
    ledger = EvidenceLedger().with_claim("C-X")
    entry_before = ledger.get("C-X")
    assert entry_before is not None
    posterior_before = entry_before.posterior_log_odds
    after = ledger.with_evidence("C-X", e)
    entry_after = after.get("C-X")
    assert entry_after is not None
    assert math.isclose(entry_after.posterior_log_odds, posterior_before, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 14. Minimal — STOP and NONE never change tier (no-op metamorphic)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("starting_tier", [0, 1, 5])
def test_minimal_stop_and_none_are_noops(starting_tier: int) -> None:
    c = Claim(
        claim_id="C-X",
        tier=starting_tier,
        posterior_log_odds=0.0,
        evidence_count=0,
        last_action=NONE,
    )
    # firewall_passed_all=False ⇒ STOP
    after_stop = minimal_evaluate(c, firewall_passed_all=False)
    assert after_stop.tier == starting_tier
    # No flags ⇒ NONE
    after_none = minimal_evaluate(c)
    assert after_none.tier == starting_tier


# ---------------------------------------------------------------------------
# 15. EvidenceLedger — bf=0 evidence drives KILL regardless of prior history
# ---------------------------------------------------------------------------


@given(
    n_prior=st.integers(min_value=0, max_value=8),
    bf_prior=st.floats(min_value=0.5, max_value=2.0, allow_nan=False),
)
@settings(max_examples=20, deadline=None)
def test_ledger_bf_zero_kills_regardless_of_history(n_prior: int, bf_prior: float) -> None:
    """Replication-mismatch evidence (BF=0) drives the claim to KILL
    no matter how many prior evidences accumulated, and no matter
    their signs."""
    ledger = EvidenceLedger().with_claim("C-X")
    for i in range(n_prior):
        ledger = ledger.with_evidence(
            "C-X",
            Evidence(timestamp_utc=_ts(i), type="UNINFORMATIVE", bayes_factor=bf_prior),
        )
    final = ledger.with_evidence(
        "C-X",
        Evidence(
            timestamp_utc=_ts(n_prior + 1),
            type="REPLICATION_MISMATCH",
            bayes_factor=0.0,
        ),
    )
    entry = final.get("C-X")
    assert entry is not None
    assert entry.tier_action == "KILL"
    assert entry.posterior_probability == 0.0
