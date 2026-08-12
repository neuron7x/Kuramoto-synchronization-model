# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witnesses for the PNCC thermodynamic-control laws in the catalog.

Each binds a pytest function to a first-principles catalog law via ``@law`` and
proves it holds in the real ``core.physics`` PNCC kernel, citing an EXISTING
registry invariant (no new invariant, no count change). Two previously-unwitnessed
laws gain witnesses:

* ``pncc.reversible_gate_byte_exact`` — a reversible-tagged action's rollback
  recovers the byte-exact pre-state: rollback(trace.audit_hash).state_bytes ==
  pre_state, over many random reversible actions (INV-REVERSIBLE-GATE; Bennett
  1973). Witnessed on ``core.physics.reversible_gate.ReversibleGate``.
* ``pncc.landauer_proxy_dominance`` — an irreversible action's aggregate proxy
  cost dominates its reversible alternative: C_irr ≥ C_rev, strictly so iff the
  irreversibility_score > 0, with equality exactly at score == 0 (INV-LANDAUER-
  PROXY; Landauer 1961). Witnessed on ``core.physics.thermodynamic_budget``.

Nothing here is a market claim. These are reversibility-accounting contract facts
about the cognitive-controller kernel.
"""

from __future__ import annotations

import numpy as np

from core.physics.reversible_gate import ReversibleGate, ReversibleGateConfig
from core.physics.thermodynamic_budget import (
    ThermodynamicBudgetConfig,
    aggregate_entry,
    compute_entropy_cost,
    compute_irreversibility_cost,
    compute_latency_cost,
    compute_token_cost,
    reversible_alternative_cost,
)
from physics_contracts.law import law

# Byte recovery is strict equality — no tolerance is admissible.
# Cost dominance is a definitional inequality; only float round-off is tolerated.
COST_EPS = 1e-12


@law("pncc.reversible_gate_byte_exact", n_actions=1000, max_state_bytes=64)
def test_reversible_action_rollback_recovers_byte_exact_pre_state() -> None:
    """INV-REVERSIBLE-GATE: rollback recovers the byte-exact pre-state.

    Generates many random reversible-tagged actions (irreversibility_score below
    the configured threshold, rollback payload supplied) and requires that
    rollback(trace.audit_hash).state_bytes reproduces the pre-state byte-for-byte.
    A single mismatched byte fails the law — recovery must be exact, not close.
    """
    n_actions = 1000
    max_state_bytes = 64
    cfg = ReversibleGateConfig()
    gate = ReversibleGate(cfg)
    rng = np.random.default_rng(seed=0)
    mismatches = 0
    for index in range(n_actions):
        pre_state = rng.bytes(int(rng.integers(1, max_state_bytes + 1)))
        payload = rng.bytes(int(rng.integers(1, max_state_bytes // 2 + 1)))
        post_state = rng.bytes(int(rng.integers(1, max_state_bytes + 1)))
        score = float(rng.uniform(0.0, cfg.irreversibility_threshold))
        trace = gate.gate(
            action_id=f"action-{index}",
            pre_state=pre_state,
            action_payload=payload,
            post_state=post_state,
            irreversibility_score=score,
            timestamp_ns=1_000 + index,
            rollback_payload=pre_state,
        )
        if gate.rollback(trace.audit_hash).state_bytes != pre_state:
            mismatches += 1

    assert mismatches == 0, (
        "INV-REVERSIBLE-GATE violated: observed mismatched recoveries = "
        f"{mismatches} must be 0 over n_actions={n_actions} with seed=0; "
        "reversible rollback must recover the pre-state byte-for-byte"
    )


@law("pncc.landauer_proxy_dominance", n_actions=500, penalty_floor=COST_EPS)
def test_irreversible_cost_dominates_reversible_alternative() -> None:
    """INV-LANDAUER-PROXY: C_irr ≥ C_rev, strict iff irreversibility_score > 0.

    For a sweep of actions with random token/latency/entropy components and
    irreversibility scores drawn from {0} ∪ (0, 1], the aggregate proxy cost of
    the irreversible action must never fall below its reversible alternative.
    When the score is positive the inequality must be strict; when the score is
    exactly zero the two costs must coincide. Tracks the worst excursions of both.
    """
    n_actions = 500
    cfg = ThermodynamicBudgetConfig()
    rng = np.random.default_rng(seed=1)
    worst_deficit = 0.0
    worst_positive_gap = np.inf
    worst_zero_gap = 0.0
    n_positive = 0
    for index in range(n_actions):
        score = 0.0 if bool(rng.integers(0, 2)) else float(rng.uniform(1e-6, 1.0))
        is_irreversible = score > 0.0
        token = compute_token_cost(int(rng.integers(0, 500)), int(rng.integers(0, 500)))
        latency = compute_latency_cost(int(rng.integers(0, 1_000_000)), int(rng.integers(0, 1_000_000)))
        entropy = compute_entropy_cost(float(rng.uniform(0.0, 100.0)), float(rng.uniform(0.0, 100.0)))
        irreversible = compute_irreversibility_cost(is_irreversible, score, cfg)
        entry = aggregate_entry(f"action-{index}", 1_000 + index, token, latency, entropy, irreversible)
        c_irr = entry.total_proxy_cost
        c_rev = reversible_alternative_cost(entry, cfg)
        worst_deficit = max(worst_deficit, c_rev - c_irr)
        if score > 0.0:
            n_positive += 1
            worst_positive_gap = min(worst_positive_gap, c_irr - c_rev)
        else:
            worst_zero_gap = max(worst_zero_gap, abs(c_irr - c_rev))

    assert worst_deficit <= COST_EPS, (
        "INV-LANDAUER-PROXY violated: observed worst (C_rev − C_irr) = "
        f"{worst_deficit:.3e} must be ≤ {COST_EPS:.0e} over n_actions={n_actions} "
        "with seed=1; irreversible cost must dominate the reversible alternative"
    )
    assert worst_positive_gap > 0.0, (
        "INV-LANDAUER-PROXY violated: observed min positive-score gap (C_irr − C_rev) = "
        f"{worst_positive_gap:.3e} must be > 0 over n_positive={n_positive} "
        "with seed=1; dominance must be strict whenever irreversibility_score > 0"
    )
    assert worst_zero_gap <= COST_EPS, (
        "INV-LANDAUER-PROXY violated: observed worst zero-score |C_irr − C_rev| = "
        f"{worst_zero_gap:.3e} must be ≤ {COST_EPS:.0e} over n_actions={n_actions} "
        "with seed=1; the costs must coincide exactly when irreversibility_score == 0"
    )
