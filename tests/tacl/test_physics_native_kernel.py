# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""Tests for ``tacl.physics_native_kernel`` — PNCC-F Wave 2 composition.

INV-FREE-ENERGY (kernel selection scope):
    The chosen action MUST be the unique-or-fail-closed argmin of the
    composite score over a non-empty candidate set. Ties within
    ``cfg.tie_tolerance`` collapse to DORMANT (chosen is None).

Tests in this module cover:

- algebraic single-candidate recovery,
- universal sweep over unique-minimum cases,
- tie-tolerance collapse (both fail-closed and disabled paths),
- composability: lambda_thermo=0 + lambda_irrev=0 reduces to pure
  DR-FREE selection,
- qualitative penalty effect of lambda_irreversibility,
- DORMANT propagation from upstream ``robust_energy_state``,
- INV-HPC1 deterministic output under fixed seed,
- INV-FREE-ENERGY 1000-draw falsification micro-battery,
- audit-hash recording for non-DORMANT decisions,
- absence of hidden global state across two kernel instances,
- empty candidate fail-closed DORMANT.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Final

import pytest

from tacl.dr_free import AmbiguitySet, DRFreeEnergyModel
from tacl.energy_model import EnergyMetrics
from tacl.physics_native_kernel import (
    CandidateAction,
    CompositeScore,
    KernelDecision,
    PhysicsNativeKernel,
    PhysicsNativeKernelConfig,
    evaluate_candidate,
    select_action,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


_NOMINAL_METRICS: Final[EnergyMetrics] = EnergyMetrics(
    latency_p95=10.0,
    latency_p99=20.0,
    coherency_drift=0.01,
    cpu_burn=0.10,
    mem_cost=1.0,
    queue_depth=4.0,
    packet_loss=0.0001,
)


def _zero_ambiguity() -> AmbiguitySet:
    return AmbiguitySet(radii={}, mode="box")


def _make_candidate(
    action_id: str = "a",
    *,
    irreversibility_score: float = 0.0,
    n_in: int = 10,
    n_out: int = 5,
    wall_ns: int = 1_000_000,
    bits_consumed: float = 0.0,
    bits_erased: float = 0.0,
    payload: bytes = b"x",
) -> CandidateAction:
    return CandidateAction(
        action_id=action_id,
        payload=payload,
        irreversibility_score=irreversibility_score,
        n_input_tokens=n_in,
        n_output_tokens=n_out,
        expected_wall_time_ns=wall_ns,
        bits_consumed=bits_consumed,
        bits_erased=bits_erased,
    )


def _bracketed_random_candidates(
    rng: random.Random,
    n: int,
    *,
    composite_spread: float = 1.0,
) -> Sequence[CandidateAction]:
    """Generate ``n`` candidates with payloads / token counts varying so
    that their thermodynamic-cost components meaningfully differ. The
    first candidate is forced to have a uniquely-low irreversibility
    score so that, with ``lambda_irreversibility >> 0``, it becomes the
    unique argmin. The DR-FREE component is shared across candidates
    (same metrics) so ``f_robust`` is identical.
    """
    out: list[CandidateAction] = []
    for i in range(n):
        out.append(
            _make_candidate(
                action_id=f"a{i:03d}",
                # Sprinkle a small offset so composite scores rarely tie.
                irreversibility_score=rng.uniform(0.0, 1.0) * composite_spread,
                n_in=rng.randint(1, 50),
                n_out=rng.randint(1, 50),
                wall_ns=rng.randint(1_000, 10_000_000),
                bits_consumed=rng.uniform(0.0, 5.0),
                bits_erased=rng.uniform(0.0, 5.0),
                payload=bytes([rng.randint(0, 255) for _ in range(rng.randint(1, 16))]),
            )
        )
    return out


# ---------------------------------------------------------------------------
# 1. Single-candidate recovers DR-FREE selection (algebraic)
# ---------------------------------------------------------------------------


def test_single_candidate_recovers_dr_free() -> None:
    """One candidate, lambda_thermo=lambda_irrev=0 => that candidate is
    chosen and the audit_hash is set when going through ``decide``.
    """
    cfg = PhysicsNativeKernelConfig()
    kernel = PhysicsNativeKernel(cfg)
    cand = _make_candidate(action_id="only")

    decision = kernel.decide([cand], _NOMINAL_METRICS)

    assert decision.chosen is cand, "single candidate must be selected"
    assert decision.audit_hash is not None, "non-DORMANT decision must record audit_hash"
    assert decision.decision_trace is not None
    assert decision.decision_trace.audit_hash == decision.audit_hash
    assert decision.state in {"NORMAL", "WARNING"}
    assert decision.reason == ""
    # Composite for the only candidate must equal its f_robust under
    # zero-weight defaults.
    [score] = decision.scores
    assert abs(score.composite - score.f_robust) < 1e-12, (
        f"INV-FREE-ENERGY pure-DR-FREE recovery violated: "
        f"composite={score.composite!r}, f_robust={score.f_robust!r}, "
        f"diff={abs(score.composite - score.f_robust)!r}"
    )


# ---------------------------------------------------------------------------
# 2. Universal sweep: argmin is chosen for every unique-minimum case
# ---------------------------------------------------------------------------


def test_argmin_is_chosen_for_unique_minimum() -> None:
    """Sweep K candidate sets; whenever the minimum composite is
    strictly lower than the runner-up by > tie_tolerance, that
    candidate must be chosen.
    """
    rng = random.Random(20260425)
    cfg = PhysicsNativeKernelConfig(
        lambda_thermo=0.5,
        lambda_irreversibility=2.0,  # strong tilt to break ties
    )
    kernel = PhysicsNativeKernel(cfg)
    n_unique_minima = 0
    for trial in range(60):
        n = rng.randint(2, 8)
        candidates = list(_bracketed_random_candidates(rng, n))
        decision = kernel.decide(candidates, _NOMINAL_METRICS, timestamp_ns=trial)
        composites = [s.composite for s in decision.scores]
        min_c = min(composites)
        near_min = [c for c in composites if c <= min_c + cfg.tie_tolerance]
        if len(near_min) == 1:
            n_unique_minima += 1
            assert decision.chosen is not None, (
                f"INV-FREE-ENERGY VIOLATED: unique min exists but chosen is None; "
                f"composites={composites!r}, trial={trial}"
            )
            chosen_score = next(s for s in decision.scores if s.candidate is decision.chosen)
            assert abs(chosen_score.composite - min_c) < 1e-12, (
                f"INV-FREE-ENERGY VIOLATED: chosen.composite={chosen_score.composite!r} "
                f"!= min={min_c!r}, trial={trial}"
            )
    assert n_unique_minima > 0, (
        "test fixture too weak — no unique minima generated; "
        "increase composite_spread or candidate variation."
    )


# ---------------------------------------------------------------------------
# 3. Tie-tolerance triggers DORMANT (universal — INV-FREE-ENERGY tie path)
# ---------------------------------------------------------------------------


def test_tie_tolerance_triggers_dormant() -> None:
    """Two candidates with identical decision-relevant fields => tie =>
    DORMANT under fail_closed_on_tie=True (default).
    """
    cfg = PhysicsNativeKernelConfig(
        lambda_thermo=1.0,
        lambda_irreversibility=1.0,
    )
    kernel = PhysicsNativeKernel(cfg)
    a = _make_candidate(action_id="a")
    b = _make_candidate(action_id="b")  # identical numeric fields, different id
    decision = kernel.decide([a, b], _NOMINAL_METRICS)

    composites = [s.composite for s in decision.scores]
    fixture_msg = f"fixture inconsistency: ties were not actually tied (composites={composites!r})"
    assert abs(composites[0] - composites[1]) < cfg.tie_tolerance, fixture_msg
    assert decision.chosen is None, (
        f"INV-FREE-ENERGY VIOLATED: tied composites must collapse to DORMANT, "
        f"got chosen={decision.chosen!r}"
    )
    assert decision.state == "DORMANT"
    assert decision.audit_hash is None
    assert decision.decision_trace is None
    assert "tie" in decision.reason.lower()


# ---------------------------------------------------------------------------
# 4. Tie tolerance disabled => first argmin is picked
# ---------------------------------------------------------------------------


def test_tie_tolerance_disabled_picks_first() -> None:
    """``fail_closed_on_tie=False`` => the first argmin in candidate
    order is chosen instead of DORMANT.
    """
    cfg = PhysicsNativeKernelConfig(
        lambda_thermo=1.0,
        lambda_irreversibility=1.0,
        fail_closed_on_tie=False,
    )
    kernel = PhysicsNativeKernel(cfg)
    a = _make_candidate(action_id="a")
    b = _make_candidate(action_id="b")
    decision = kernel.decide([a, b], _NOMINAL_METRICS)

    assert decision.chosen is a, (
        f"INV-FREE-ENERGY (tie-disabled) VIOLATED: first argmin must be chosen, "
        f"got {decision.chosen!r}"
    )
    assert decision.state in {"NORMAL", "WARNING"}
    assert decision.audit_hash is not None


# ---------------------------------------------------------------------------
# 5. lambda_thermo=0 + lambda_irrev=0 => composite EXACTLY equals f_robust
#    (algebraic, exact; pure DR-FREE recovery)
# ---------------------------------------------------------------------------


def test_lambda_thermo_zero_recovers_pure_dr_free() -> None:
    """Composability check (algebraic): with both weights 0, every
    candidate's composite must equal its f_robust to float precision.
    """
    cfg = PhysicsNativeKernelConfig(lambda_thermo=0.0, lambda_irreversibility=0.0)
    fem = DRFreeEnergyModel()
    cands = [
        _make_candidate(action_id="x", irreversibility_score=0.0),
        _make_candidate(
            action_id="y",
            irreversibility_score=0.7,
            wall_ns=10_000_000,
            n_in=100,
            n_out=200,
            bits_erased=4.0,
        ),
    ]
    for c in cands:
        score = evaluate_candidate(
            c, _NOMINAL_METRICS, _zero_ambiguity(), cfg, free_energy_model=fem
        )
        assert score.composite == score.f_robust, (
            f"INV-FREE-ENERGY pure-DR-FREE recovery (algebraic) VIOLATED: "
            f"composite={score.composite!r}, f_robust={score.f_robust!r} "
            f"with lambda_thermo=0 and lambda_irreversibility=0"
        )


# ---------------------------------------------------------------------------
# 6. lambda_irreversibility penalizes irreversible actions (qualitative)
# ---------------------------------------------------------------------------


def test_lambda_irrev_penalizes_irreversible_actions() -> None:
    """With lambda_irreversibility >> 0 and lambda_thermo=0, the
    candidate with the lower irreversibility_score must be chosen
    when the two candidates are otherwise identical.
    """
    cfg = PhysicsNativeKernelConfig(
        lambda_thermo=0.0,
        lambda_irreversibility=10.0,
    )
    kernel = PhysicsNativeKernel(cfg)
    safe = _make_candidate(action_id="safe", irreversibility_score=0.0)
    risky = _make_candidate(action_id="risky", irreversibility_score=0.9)
    decision = kernel.decide([safe, risky], _NOMINAL_METRICS)

    assert decision.chosen is safe, (
        f"INV-FREE-ENERGY qualitative VIOLATED: lambda_irreversibility={cfg.lambda_irreversibility} "
        f"should penalize risky over safe; got chosen={decision.chosen!r}"
    )


# ---------------------------------------------------------------------------
# 7. DORMANT when robust_state == DORMANT (composes with robust_energy_state)
# ---------------------------------------------------------------------------


def test_dormant_when_robust_state_dormant() -> None:
    """When ``robust_energy_state`` returns DORMANT, the kernel must
    fail-closed regardless of candidate composition.
    """
    # Astronomically low crisis_threshold => every robust_F triggers DORMANT.
    cfg = PhysicsNativeKernelConfig(
        warning_threshold=-1.0e30,
        crisis_threshold=-1.0e30,
    )
    kernel = PhysicsNativeKernel(cfg)
    decision = kernel.decide([_make_candidate("a"), _make_candidate("b")], _NOMINAL_METRICS)

    assert decision.chosen is None, (
        f"INV-FREE-ENERGY robust-DORMANT VIOLATED: chosen must be None when "
        f"robust_state == DORMANT, got chosen={decision.chosen!r}"
    )
    assert decision.state == "DORMANT"
    assert "DORMANT" in decision.reason


# ---------------------------------------------------------------------------
# 8. Decision is deterministic under fixed seed (INV-HPC1)
# ---------------------------------------------------------------------------


def test_decision_is_deterministic_under_fixed_seed() -> None:
    """Two kernel instances given identical inputs must produce
    identical audit_hash values. The kernel uses no global state, no
    RNG, no time call — INV-HPC1.
    """
    cfg = PhysicsNativeKernelConfig(
        lambda_thermo=0.3,
        lambda_irreversibility=1.5,
    )
    rng = random.Random(424242)
    cands = list(_bracketed_random_candidates(rng, 5))

    k1 = PhysicsNativeKernel(cfg)
    k2 = PhysicsNativeKernel(cfg)
    d1 = k1.decide(cands, _NOMINAL_METRICS, timestamp_ns=12345)
    d2 = k2.decide(cands, _NOMINAL_METRICS, timestamp_ns=12345)

    assert d1.chosen is not None
    assert d2.chosen is not None
    assert d1.audit_hash == d2.audit_hash, (
        f"INV-HPC1 VIOLATED: deterministic kernel produced different "
        f"audit_hashes: {d1.audit_hash!r} vs {d2.audit_hash!r}"
    )
    # Composite scores must be exactly equal (same float ops).
    for s1, s2 in zip(d1.scores, d2.scores, strict=True):
        composite_msg = (
            f"INV-HPC1 VIOLATED: composite mismatch: {s1.composite!r} vs {s2.composite!r}"
        )
        assert s1.composite == s2.composite, composite_msg


# ---------------------------------------------------------------------------
# 9. INV-FREE-ENERGY 1000-draw falsification micro-battery (universal)
# ---------------------------------------------------------------------------


def test_invariant_falsification_random_1000() -> None:
    """1000 random ``(candidates, metrics, ambiguity)`` draws.

    Every ``select_action`` result must satisfy INV-FREE-ENERGY:
      * non-empty candidates
      * either chosen.composite == min(composites) (within tie_tol),
      * OR chosen is None AND state == DORMANT AND >= 2 candidates
        within tie_tol of min.

    Falsification: any decision where chosen.composite > min(composites)
    + tie_tolerance with state != DORMANT counts as a violation.
    """
    rng = random.Random(20260425)
    cfg = PhysicsNativeKernelConfig(
        lambda_thermo=1.0,
        lambda_irreversibility=1.0,
        tie_tolerance=1e-12,
    )
    fem = DRFreeEnergyModel()
    n_violations = 0
    n_dormant_on_tie = 0
    n_unique = 0
    n_robust_dormant = 0

    for trial in range(1000):
        n = rng.randint(1, 6)
        candidates = list(_bracketed_random_candidates(rng, n))
        # Vary metrics modestly so that f_robust changes batch-to-batch.
        metrics = EnergyMetrics(
            latency_p95=rng.uniform(1.0, 50.0),
            latency_p99=rng.uniform(50.0, 100.0),
            coherency_drift=rng.uniform(0.0, 0.05),
            cpu_burn=rng.uniform(0.0, 0.5),
            mem_cost=rng.uniform(0.1, 5.0),
            queue_depth=rng.uniform(0.0, 16.0),
            packet_loss=rng.uniform(0.0, 0.001),
        )
        ambiguity = AmbiguitySet(radii={"latency_p95": rng.uniform(0.0, 0.2)}, mode="box")
        decision = select_action(candidates, metrics, ambiguity, cfg, free_energy_model=fem)
        composites = [s.composite for s in decision.scores]
        min_c = min(composites)
        near_min = [c for c in composites if c <= min_c + cfg.tie_tolerance]

        if decision.state == "DORMANT" and decision.chosen is None:
            if len(near_min) >= 2:
                n_dormant_on_tie += 1
                continue
            # DORMANT for non-tie reason (robust_state DORMANT). Allowed.
            n_robust_dormant += 1
            continue

        # Normal pass-through: chosen must be the unique argmin.
        assert decision.chosen is not None, (
            f"INV-FREE-ENERGY VIOLATED: state={decision.state} but chosen is None; "
            f"trial={trial}, composites={composites!r}"
        )
        chosen_score = next(s for s in decision.scores if s.candidate is decision.chosen)
        if chosen_score.composite > min_c + cfg.tie_tolerance:
            n_violations += 1
        else:
            n_unique += 1

    assert n_violations == 0, (
        f"INV-FREE-ENERGY VIOLATED in {n_violations}/1000 random scenarios "
        f"(unique={n_unique}, dormant_on_tie={n_dormant_on_tie}, "
        f"robust_dormant={n_robust_dormant})"
    )
    # Sanity: the test must have actually exercised the unique-argmin
    # branch a non-trivial number of times.
    assert n_unique >= 200, (
        f"falsification battery too weak: only {n_unique}/1000 unique-argmin "
        f"draws were observed (dormant_on_tie={n_dormant_on_tie}, "
        f"robust_dormant={n_robust_dormant})"
    )


# ---------------------------------------------------------------------------
# 10. audit_hash is recorded for non-DORMANT (algebraic)
# ---------------------------------------------------------------------------


def test_audit_hash_is_recorded_for_non_dormant() -> None:
    """Every non-DORMANT decision returned by ``decide`` must carry a
    sha256 hex audit hash and a populated ``decision_trace``.
    """
    # lambda_irreversibility>0 breaks the tie between two otherwise
    # identical-composite candidates so that the kernel does NOT fail
    # closed on tie. Without this lever, both candidates' composites
    # collapse to the same f_robust and the decision DORMANTs.
    cfg = PhysicsNativeKernelConfig(lambda_irreversibility=1.0)
    kernel = PhysicsNativeKernel(cfg)
    cand_a = _make_candidate(action_id="a", irreversibility_score=0.01)
    cand_b = _make_candidate(action_id="b", irreversibility_score=0.5, n_in=20)
    decision = kernel.decide([cand_a, cand_b], _NOMINAL_METRICS, timestamp_ns=7)

    assert decision.chosen is not None
    assert decision.audit_hash is not None
    # sha256 hex digest = 64 chars in [0-9a-f].
    assert len(decision.audit_hash) == 64
    assert all(ch in "0123456789abcdef" for ch in decision.audit_hash)
    assert decision.decision_trace is not None
    assert decision.decision_trace.audit_hash == decision.audit_hash


# ---------------------------------------------------------------------------
# 11. No hidden global state across kernel instances (universal)
# ---------------------------------------------------------------------------


def test_no_hidden_global_state_across_kernel_instances() -> None:
    """Two independent kernels must not see each other's gate ledgers.

    After kernel A admits a trace, kernel B must not have it in its
    ledger; and admitting the same logical action in kernel B must
    not raise (no cross-instance collision).
    """
    cfg = PhysicsNativeKernelConfig()
    k_a = PhysicsNativeKernel(cfg)
    k_b = PhysicsNativeKernel(cfg)
    cand = _make_candidate(action_id="cross", irreversibility_score=0.01)

    da = k_a.decide([cand], _NOMINAL_METRICS, timestamp_ns=1)
    assert da.audit_hash is not None
    assert k_a.gate.is_known(da.audit_hash)
    leak_msg = "cross-instance ledger leak: kernel B should not know audit_hash from kernel A"
    assert not k_b.gate.is_known(da.audit_hash), leak_msg

    db = k_b.decide([cand], _NOMINAL_METRICS, timestamp_ns=1)
    assert db.audit_hash is not None
    hpc1_msg = "INV-HPC1: same inputs yield same audit_hash even on different instances"
    assert db.audit_hash == da.audit_hash, hpc1_msg
    assert k_b.gate.is_known(db.audit_hash)


# ---------------------------------------------------------------------------
# 12. Empty candidates returns DORMANT (universal — fail-closed)
# ---------------------------------------------------------------------------


def test_empty_candidates_returns_dormant() -> None:
    """Empty candidate list => fail-closed DORMANT with no audit hash."""
    cfg = PhysicsNativeKernelConfig()
    kernel = PhysicsNativeKernel(cfg)
    decision = kernel.decide([], _NOMINAL_METRICS)

    assert decision.chosen is None
    assert decision.state == "DORMANT"
    assert decision.scores == ()
    assert decision.audit_hash is None
    assert decision.decision_trace is None
    assert "empty" in decision.reason.lower()


# ---------------------------------------------------------------------------
# Extra fail-closed sanity checks (validation surface)
# ---------------------------------------------------------------------------


def test_validation_rejects_negative_lambda() -> None:
    with pytest.raises(ValueError, match="lambda_thermo"):
        PhysicsNativeKernel(PhysicsNativeKernelConfig(lambda_thermo=-1.0))
    with pytest.raises(ValueError, match="lambda_irreversibility"):
        PhysicsNativeKernel(PhysicsNativeKernelConfig(lambda_irreversibility=-0.1))


def test_validation_rejects_out_of_range_score() -> None:
    cfg = PhysicsNativeKernelConfig()
    kernel = PhysicsNativeKernel(cfg)
    bad = _make_candidate(action_id="bad", irreversibility_score=1.5)
    with pytest.raises(ValueError, match=r"irreversibility_score"):
        kernel.decide([bad], _NOMINAL_METRICS)


def test_select_action_pure_does_not_record_audit() -> None:
    """``select_action`` is the pure entry point — no audit_hash
    populated even on a successful selection."""
    cfg = PhysicsNativeKernelConfig()
    fem = DRFreeEnergyModel()
    cand = _make_candidate(action_id="one")
    decision: KernelDecision = select_action(
        [cand], _NOMINAL_METRICS, _zero_ambiguity(), cfg, free_energy_model=fem
    )
    assert decision.chosen is cand
    assert decision.audit_hash is None
    assert decision.decision_trace is None
    [score] = decision.scores
    assert isinstance(score, CompositeScore)
