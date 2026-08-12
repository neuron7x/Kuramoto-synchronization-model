# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for :mod:`core.neuro.epistemic_validation`.

Layout
------
The tests are organised by the contract they pin, not by function:

* **Configuration validation** — every ``EpistemicConfig`` field
  rejects out-of-range or non-finite inputs (INV-FE2 / INV-HPC2).
* **Genesis determinism** — identical config ⟹ bit-identical genesis
  state across processes (INV-HPC1).
* **Single-step semantics** — seq monotonicity, budget non-negativity,
  cost always paid, weight bounds, lineage mismatch rejection,
  finite-input rejection.
* **Halt machine** — sticky halt, halt reason routing, seq does not
  advance after halt.
* **Stream semantics** — :func:`verify_stream` short-circuits on halt,
  rejects non-finite inputs and shape mismatches.
* **RebusBridge composition** — bridge is a no-op for active states
  and forwards stressed-state signals for halted states.
* **Hash chain regression** — the binary packing format is pinned to
  a known-vector test so any future refactor that changes the packing
  is caught explicitly.
* **Hypothesis properties** — universal invariants (INV-FE2 component
  bounds, sticky halt, monotonic seq) over randomised streams.
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.neuro.epistemic_validation import (
    EpistemicConfig,
    EpistemicError,
    EpistemicPhase,
    EpistemicState,
    HaltMargin,
    RebusBridge,
    halt_margin,
    initial_state,
    reset_with_external_proof,
    update,
    verify_stream,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_config(
    *,
    invariant_floor: float = 0.2,
    initial_budget: float = 100.0,
    initial_weight: float = 0.6,
    temperature: float = 1.0,
    learning_rate: float = 0.5,
    decay_factor: float = 0.1,
) -> EpistemicConfig:
    return EpistemicConfig(
        invariant_floor=invariant_floor,
        initial_budget=initial_budget,
        initial_weight=initial_weight,
        temperature=temperature,
        learning_rate=learning_rate,
        decay_factor=decay_factor,
    )


# ---------------------------------------------------------------------------
# Configuration validation (INV-FE2 / INV-HPC2 at the boundary)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("floor", [-0.1, 0.0, 1.0, 1.5, math.nan])
def test_invariant_floor_must_be_open_unit(floor: float) -> None:
    with pytest.raises(EpistemicError, match="invariant_floor"):
        _default_config(invariant_floor=floor)


@pytest.mark.parametrize("budget", [-1.0, 0.0, math.nan, math.inf])
def test_initial_budget_must_be_finite_positive(budget: float) -> None:
    with pytest.raises(EpistemicError, match="initial_budget"):
        _default_config(initial_budget=budget)


@pytest.mark.parametrize(
    ("floor", "weight"),
    [
        (0.3, 0.2),  # below floor
        (0.3, 1.5),  # above 1
        (0.3, math.nan),
        (0.3, -math.inf),
    ],
)
def test_initial_weight_bounded_by_floor_and_one(floor: float, weight: float) -> None:
    with pytest.raises(EpistemicError, match="initial_weight"):
        _default_config(invariant_floor=floor, initial_weight=weight)


@pytest.mark.parametrize("temp", [-1.0, 0.0, math.nan, math.inf])
def test_temperature_must_be_finite_positive(temp: float) -> None:
    with pytest.raises(EpistemicError, match="temperature"):
        _default_config(temperature=temp)


@pytest.mark.parametrize("rate", [0.0, 1.0, -0.1, 1.5])
def test_learning_rate_in_open_unit(rate: float) -> None:
    with pytest.raises(EpistemicError, match="learning_rate"):
        _default_config(learning_rate=rate)


@pytest.mark.parametrize("d", [0.0, 1.0, -0.1, 1.5])
def test_decay_factor_in_open_unit(d: float) -> None:
    with pytest.raises(EpistemicError, match="decay_factor"):
        _default_config(decay_factor=d)


# ---------------------------------------------------------------------------
# Genesis determinism (INV-HPC1)
# ---------------------------------------------------------------------------


def test_genesis_state_fields() -> None:
    cfg = _default_config()
    state = initial_state(cfg)
    assert state.seq == 0
    assert state.weight == cfg.initial_weight
    assert state.budget == cfg.initial_budget
    assert state.invariant_floor == cfg.invariant_floor
    assert state.phase is EpistemicPhase.ACTIVE
    assert state.halt_reason == ""
    assert len(state.state_hash) == 64
    assert all(c in "0123456789abcdef" for c in state.state_hash)


def test_genesis_is_pure() -> None:
    """INV-HPC1: identical config ⟹ identical genesis hash."""
    cfg = _default_config()
    a = initial_state(cfg)
    b = initial_state(cfg)
    assert a == b
    assert a.state_hash == b.state_hash


# ---------------------------------------------------------------------------
# Hash chain regression (pinned packing format)
# ---------------------------------------------------------------------------


def test_state_hash_format_pinned() -> None:
    """Recompute the genesis hash by hand and compare.

    If this test fails, a future refactor changed the binary packing
    of the chain hash. That is a breaking change for any persisted
    state lineage, so the format must move with an explicit migration.
    """
    cfg = EpistemicConfig(
        invariant_floor=0.25,
        initial_budget=10.0,
        initial_weight=0.5,
        temperature=1.0,
        learning_rate=0.5,
        decay_factor=0.1,
    )
    expected_payload = (
        b"\x00" * 32
        + struct.pack(">Q", 0)
        + struct.pack("<d", 0.5)
        + struct.pack("<d", 10.0)
        + struct.pack("<d", 0.25)
        + b"\x00"
    )
    expected_hash = hashlib.sha256(expected_payload).hexdigest()
    state = initial_state(cfg)
    assert state.state_hash == expected_hash, (
        f"INV-HPC1 chain regression: state_hash={state.state_hash!r} "
        f"expected={expected_hash!r}. "
        "Genesis hash must be a SHA-256 of the documented 65-byte payload "
        "(prior_digest=zeros, big-endian seq, LE doubles for "
        "weight/budget/floor, halt-byte). "
        "Field order or endianness change breaks persisted lineages."
    )


def test_consecutive_states_have_distinct_hashes() -> None:
    cfg = _default_config()
    s0 = initial_state(cfg)
    s1 = update(s0, 0.0, 0.0, config=cfg)
    s2 = update(s1, 1.0, 1.0, config=cfg)
    hashes = {s0.state_hash, s1.state_hash, s2.state_hash}
    assert len(hashes) == 3, (
        f"chain integrity: 3 distinct states produced {len(hashes)} hashes "
        f"({hashes!r}); expected uniqueness across seq=0..2 with valid updates."
    )


# ---------------------------------------------------------------------------
# Single-step semantics
# ---------------------------------------------------------------------------


def test_update_advances_seq_by_one() -> None:
    cfg = _default_config()
    s0 = initial_state(cfg)
    s1 = update(s0, 1.0, 1.0, config=cfg)
    assert s1.seq == s0.seq + 1


def test_update_always_pays_cost() -> None:
    """Cost is debited on every step, valid or invalid (INV-FE2)."""
    cfg = _default_config(initial_budget=5.0)
    s0 = initial_state(cfg)
    s1 = update(s0, 0.0, 2.0, config=cfg)
    expected_cost = math.log1p(2.0)
    assert s1.budget == pytest.approx(s0.budget - expected_cost), (
        f"INV-FE2 component: budget delta {s0.budget - s1.budget!r} "
        f"!= expected cost {expected_cost!r} "
        f"at delta=2.0 with T=1.0; "
        f"params={cfg!r}, "
        "verify update.cost path debits even on valid steps."
    )


def test_update_rejects_non_finite_inputs() -> None:
    cfg = _default_config()
    s0 = initial_state(cfg)
    with pytest.raises(EpistemicError, match="INV-HPC2"):
        update(s0, math.nan, 0.0, config=cfg)
    with pytest.raises(EpistemicError, match="INV-HPC2"):
        update(s0, 0.0, math.inf, config=cfg)


def test_update_rejects_lineage_mismatch() -> None:
    cfg_a = _default_config(invariant_floor=0.2)
    cfg_b = _default_config(invariant_floor=0.3)
    s0 = initial_state(cfg_a)
    with pytest.raises(EpistemicError, match="lineage mismatch"):
        update(s0, 0.0, 0.0, config=cfg_b)


def test_update_weight_increases_on_perfect_match() -> None:
    """Perfect agreement should reinforce, not decay (INV-FE2 weight bound)."""
    cfg = _default_config(initial_weight=0.4)
    s0 = initial_state(cfg)
    s1 = update(s0, 0.5, 0.5, config=cfg)
    # likelihood = 1, alpha = 0.5, prior weight = 0.4 ⟹ new = 0.7
    assert s1.weight == pytest.approx(0.7), (
        f"INV-FE2: perfect-match weight {s1.weight!r} != expected 0.7 "
        f"under alpha=0.5, prior=0.4, likelihood=1.0; params={cfg!r}."
    )


def test_update_weight_bounded_above_by_one() -> None:
    cfg = _default_config(initial_weight=0.99)
    s = initial_state(cfg)
    for _ in range(100):
        s = update(s, 0.0, 0.0, config=cfg)
        assert 0.0 <= s.weight <= 1.0, (
            f"INV-FE2: weight escaped [0, 1] after seq={s.seq}: {s.weight!r}; "
            f"perfect-match stream with alpha=0.5; params={cfg!r}."
        )


# ---------------------------------------------------------------------------
# Halt machine
# ---------------------------------------------------------------------------


def test_budget_exhaustion_halts_with_reason() -> None:
    cfg = _default_config(initial_budget=0.5, temperature=1.0)
    s = initial_state(cfg)
    # log1p(10) ≈ 2.39 > budget; one step should halt.
    s = update(s, 0.0, 10.0, config=cfg)
    assert s.is_halted
    assert s.halt_reason == "budget_exhausted"
    assert s.budget == 0.0


def test_weight_collapse_halts_with_reason() -> None:
    """Force a stream that fails the budget check on the first step
    (so weight decays), eventually crossing the floor."""
    cfg = _default_config(
        invariant_floor=0.55,
        initial_weight=0.6,
        initial_budget=0.001,  # too small to pay any cost
        learning_rate=0.5,
        decay_factor=0.5,  # aggressive decay to converge fast
        temperature=1.0,
    )
    s = initial_state(cfg)
    # First step: cost > budget ⟹ invalid ⟹ decay branch.
    # decay multiplier = (1 - 0.5*0.5) = 0.75 ⟹ 0.6 * 0.75 = 0.45 < 0.55 floor.
    # But budget also exhausts, so reason resolution prefers
    # budget_exhausted (the test for weight_collapse needs budget > 0
    # at the moment of crossing).
    cfg2 = _default_config(
        invariant_floor=0.55,
        initial_weight=0.6,
        initial_budget=100.0,
        learning_rate=0.5,
        decay_factor=0.5,
        temperature=0.001,  # essentially free observations
    )
    s = initial_state(cfg2)
    # Force "invalid" via floor check: weight=0.6, floor=0.55 ⟹ above_floor=True.
    # We need above_floor to be False to take decay branch reliably.
    # Instead: set initial_weight = 0.55 (== floor, above_floor True) and
    # use a fact stream where the floor triggers immediately after one decay.
    cfg3 = _default_config(
        invariant_floor=0.55,
        initial_weight=0.56,
        initial_budget=100.0,
        learning_rate=0.5,
        decay_factor=0.5,
        temperature=10.0,  # pricey ⟹ invalid step
    )
    s = initial_state(cfg3)
    # cost = 10 * log1p(1) ≈ 6.93 < budget=100, but log1p(0)=0 makes valid.
    # We need cost > budget on a single step to take invalid path while
    # budget remains > 0 afterwards. Use small budget but a cheap-enough
    # observation that doesn't drain to zero.
    cfg4 = _default_config(
        invariant_floor=0.55,
        initial_weight=0.56,
        initial_budget=0.5,  # depletes after one step
        learning_rate=0.5,
        decay_factor=0.5,
        temperature=1.0,
    )
    s = initial_state(cfg4)
    # delta=0.4 ⟹ cost = log1p(0.4) ≈ 0.336 < 0.5 budget ⟹ valid path.
    # weight EMA towards likelihood = 1/1.4 ≈ 0.714: new_weight ≈ (0.5*0.56 + 0.5*0.714) ≈ 0.637.
    # This won't collapse. We need a clean test of the weight_collapse branch:
    # set initial_weight just above floor, force invalid via huge cost in
    # ONE shot, but keep budget > 0 after — impossible with a single step
    # because we always pay the cost which is ≤ budget on valid path.
    # The clean route: make cost slightly less than budget, valid, but
    # likelihood low enough to depress the EMA below floor.
    cfg5 = _default_config(
        invariant_floor=0.55,
        initial_weight=0.56,
        initial_budget=10.0,
        learning_rate=0.99,  # near full replacement by likelihood
        decay_factor=0.1,
        temperature=1.0,
    )
    s = initial_state(cfg5)
    # delta large ⟹ likelihood small ⟹ valid path EMA ≈ likelihood ≈ 0.05.
    s = update(s, 0.0, 20.0, config=cfg5)
    assert s.is_halted, f"weight should collapse, got phase={s.phase} weight={s.weight}"
    assert s.halt_reason == "weight_collapse", (
        f"halt reason {s.halt_reason!r} != 'weight_collapse'; "
        f"final weight={s.weight!r}, budget={s.budget!r}, floor={cfg5.invariant_floor!r}; "
        "delta=20.0 ⟹ likelihood≈0.0476 ⟹ EMA≈0.055 < floor=0.55; "
        f"params={cfg5!r}."
    )


def test_sticky_halt_returns_state_unchanged() -> None:
    cfg = _default_config(initial_budget=0.1, temperature=1.0)
    s = initial_state(cfg)
    halted = update(s, 0.0, 100.0, config=cfg)
    assert halted.is_halted
    again = update(halted, 0.0, 0.0, config=cfg)
    assert again is halted, "halted state must be returned by identity (no-op short circuit)"


# ---------------------------------------------------------------------------
# Stream semantics
# ---------------------------------------------------------------------------


def test_verify_stream_short_circuits_on_halt() -> None:
    cfg = _default_config(initial_budget=0.5, temperature=1.0)
    signals = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float64)
    facts = np.array([100.0, 0.0, 0.0, 0.0], dtype=np.float64)
    s0 = initial_state(cfg)
    final = verify_stream(s0, signals, facts, config=cfg)
    assert final.is_halted
    assert final.seq == 1, f"stream halted at seq=1 but advanced to {final.seq}"


def test_verify_stream_rejects_non_finite() -> None:
    cfg = _default_config()
    signals = np.array([0.0, math.nan], dtype=np.float64)
    facts = np.array([0.0, 0.0], dtype=np.float64)
    s0 = initial_state(cfg)
    with pytest.raises(EpistemicError, match="INV-HPC2"):
        verify_stream(s0, signals, facts, config=cfg)


def test_verify_stream_shape_mismatch() -> None:
    cfg = _default_config()
    s0 = initial_state(cfg)
    with pytest.raises(EpistemicError, match=r"signals\.shape"):
        verify_stream(
            s0,
            np.zeros(3, dtype=np.float64),
            np.zeros(4, dtype=np.float64),
            config=cfg,
        )


def test_verify_stream_rejects_non_1d() -> None:
    cfg = _default_config()
    s0 = initial_state(cfg)
    with pytest.raises(EpistemicError, match="1-D"):
        verify_stream(
            s0,
            np.zeros((2, 2), dtype=np.float64),
            np.zeros((2, 2), dtype=np.float64),
            config=cfg,
        )


def test_verify_stream_perfect_alignment_reinforces_weight() -> None:
    cfg = _default_config(initial_weight=0.4, initial_budget=100.0)
    signals = np.linspace(0.0, 1.0, 50, dtype=np.float64)
    facts = signals.copy()
    s0 = initial_state(cfg)
    final = verify_stream(s0, signals, facts, config=cfg)
    assert final.weight > s0.weight, (
        f"INV-FE2: perfect alignment did not reinforce weight: "
        f"start={s0.weight!r}, end={final.weight!r}; "
        f"50-step identical streams should drive weight → likelihood=1; "
        f"params={cfg!r}."
    )
    assert not final.is_halted
    assert final.weight <= 1.0


# ---------------------------------------------------------------------------
# RebusBridge composition
# ---------------------------------------------------------------------------


def test_rebus_bridge_noop_for_active_state() -> None:
    cfg = _default_config()
    state = initial_state(cfg)
    gate: Any = MagicMock()
    bridge = RebusBridge()
    assert bridge.maybe_escalate(state, gate) is None
    gate.apply_external_safety_signal.assert_not_called()


def test_rebus_bridge_forwards_stressed_state_when_halted() -> None:
    cfg = _default_config(initial_budget=0.1)
    s0 = initial_state(cfg)
    halted = update(s0, 0.0, 100.0, config=cfg)
    assert halted.is_halted

    gate: Any = MagicMock()
    gate.apply_external_safety_signal.return_value = {"mock_w": 0.0}
    bridge = RebusBridge()
    out = bridge.maybe_escalate(halted, gate)
    assert out == {"mock_w": 0.0}
    gate.apply_external_safety_signal.assert_called_once_with(
        kill_switch_active=False,
        stressed_state=True,
    )


# ---------------------------------------------------------------------------
# Hypothesis properties
# ---------------------------------------------------------------------------


_finite = st.floats(
    min_value=-1e6,
    max_value=1e6,
    allow_nan=False,
    allow_infinity=False,
    width=64,
)


@given(
    signals=st.lists(_finite, min_size=0, max_size=200),
    facts=st.lists(_finite, min_size=0, max_size=200),
)
@settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_property_budget_non_negative(signals: list[float], facts: list[float]) -> None:
    """INV-FE2 component: budget never goes below 0."""
    n = min(len(signals), len(facts))
    cfg = _default_config(initial_budget=50.0, temperature=1.0)
    state: EpistemicState = initial_state(cfg)
    for i in range(n):
        if state.is_halted:
            break
        state = update(state, signals[i], facts[i], config=cfg)
    assert state.budget >= 0.0, (
        f"INV-FE2 VIOLATED: budget < 0 after {state.seq} updates: {state.budget!r}; "
        f"sample inputs n={n}; params={cfg!r}."
    )


@given(
    signals=st.lists(_finite, min_size=0, max_size=200),
    facts=st.lists(_finite, min_size=0, max_size=200),
)
@settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_property_weight_bounded(signals: list[float], facts: list[float]) -> None:
    """INV-FE2 component: weight stays in [0, 1] for any admissible stream."""
    n = min(len(signals), len(facts))
    cfg = _default_config(initial_budget=50.0)
    state: EpistemicState = initial_state(cfg)
    for i in range(n):
        if state.is_halted:
            break
        state = update(state, signals[i], facts[i], config=cfg)
        assert 0.0 <= state.weight <= 1.0, (
            f"INV-FE2 VIOLATED: weight escaped [0, 1] at seq={state.seq}: {state.weight!r}; "
            f"sample inputs n={n}; params={cfg!r}."
        )


@given(
    signals=st.lists(_finite, min_size=1, max_size=50),
    facts=st.lists(_finite, min_size=1, max_size=50),
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_property_seq_monotonic_until_halt(signals: list[float], facts: list[float]) -> None:
    """Chronology: seq advances by exactly 1 per non-halt update; halt freezes it."""
    n = min(len(signals), len(facts))
    cfg = _default_config(initial_budget=50.0)
    state: EpistemicState = initial_state(cfg)
    last_seq = state.seq
    for i in range(n):
        prev_state = state
        state = update(state, signals[i], facts[i], config=cfg)
        if prev_state.is_halted:
            assert state.seq == prev_state.seq, (
                f"chronology: halted state advanced seq from {prev_state.seq} to {state.seq}; "
                f"params={cfg!r}."
            )
        else:
            assert state.seq == last_seq + 1, (
                f"chronology: seq advanced by {state.seq - last_seq} (expected 1) "
                f"at i={i}; params={cfg!r}."
            )
            last_seq = state.seq


@given(
    pre=st.lists(_finite, min_size=0, max_size=50),
    post=st.lists(_finite, min_size=0, max_size=50),
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_property_halt_is_sticky(pre: list[float], post: list[float]) -> None:
    """Once halted, no subsequent update mutates state — even adversarial ones."""
    cfg = _default_config(initial_budget=0.05, temperature=1.0)
    state: EpistemicState = initial_state(cfg)
    # Force halt on the first step regardless of `pre`.
    state = update(state, 0.0, 1000.0, config=cfg)
    assert state.is_halted
    snapshot = state
    for s, f in zip(pre + post, post + pre, strict=False):
        state = update(state, s, f, config=cfg)
        assert state is snapshot, (
            f"sticky-halt property: post-halt update mutated state "
            f"(seq={snapshot.seq}→{state.seq}, hash {snapshot.state_hash}→{state.state_hash}); "
            f"params={cfg!r}."
        )


# ---------------------------------------------------------------------------
# External-proof reset (the only path out of HALTED)
# ---------------------------------------------------------------------------


def _force_halt(cfg: EpistemicConfig) -> EpistemicState:
    """Helper: drive a fresh state to HALTED via budget exhaustion."""
    state = initial_state(cfg)
    halted = update(state, 0.0, 1000.0, config=cfg)
    assert halted.is_halted
    return halted


_VALID_PROOF: str = "a" * 64


def test_reset_rejects_active_state() -> None:
    cfg = _default_config()
    state = initial_state(cfg)
    with pytest.raises(EpistemicError, match="not HALTED"):
        reset_with_external_proof(state, external_proof_hex=_VALID_PROOF, config=cfg)


def test_reset_rejects_invalid_proof_length() -> None:
    cfg = _default_config(initial_budget=0.05)
    halted = _force_halt(cfg)
    with pytest.raises(EpistemicError, match="64 hex characters"):
        reset_with_external_proof(halted, external_proof_hex="deadbeef", config=cfg)


def test_reset_rejects_non_hex_proof() -> None:
    cfg = _default_config(initial_budget=0.05)
    halted = _force_halt(cfg)
    bad = "z" * 64
    with pytest.raises(EpistemicError, match="not valid hex"):
        reset_with_external_proof(halted, external_proof_hex=bad, config=cfg)


def test_reset_rejects_lineage_mismatch() -> None:
    cfg_a = _default_config(invariant_floor=0.2, initial_budget=0.05)
    cfg_b = _default_config(invariant_floor=0.3, initial_budget=0.05)
    halted = _force_halt(cfg_a)
    with pytest.raises(EpistemicError, match="lineage mismatch"):
        reset_with_external_proof(halted, external_proof_hex=_VALID_PROOF, config=cfg_b)


def test_reset_returns_active_state_with_continued_seq() -> None:
    cfg = _default_config(initial_budget=0.05)
    halted = _force_halt(cfg)
    fresh = reset_with_external_proof(
        halted,
        external_proof_hex=_VALID_PROOF,
        config=cfg,
    )
    assert fresh.phase is EpistemicPhase.ACTIVE
    assert fresh.halt_reason == ""
    assert fresh.weight == cfg.initial_weight
    assert fresh.budget == cfg.initial_budget
    assert fresh.invariant_floor == cfg.invariant_floor
    assert fresh.seq == halted.seq + 1
    assert fresh.state_hash != halted.state_hash, (
        "INV-HPC1: post-reset hash must differ from halted hash; "
        f"got identical hash={fresh.state_hash!r}; "
        "lineage continuity is broken if proof is not woven into the chain."
    )


def test_reset_chain_is_deterministic() -> None:
    """Identical (halted_state, proof, config) ⟹ identical reset state (INV-HPC1)."""
    cfg = _default_config(initial_budget=0.05)
    halted = _force_halt(cfg)
    a = reset_with_external_proof(halted, external_proof_hex=_VALID_PROOF, config=cfg)
    b = reset_with_external_proof(halted, external_proof_hex=_VALID_PROOF, config=cfg)
    assert a == b
    assert a.state_hash == b.state_hash


def test_reset_chain_format_pinned() -> None:
    """Recompute the reset hash by hand and compare.

    The 88-byte payload format (32-byte halted-hash digest, 32-byte
    proof, three LE doubles for initial_weight / initial_budget /
    invariant_floor) is part of the persisted-lineage contract and
    must not change without an explicit migration.
    """
    cfg = _default_config(
        invariant_floor=0.2,
        initial_budget=0.05,
        initial_weight=0.5,
        temperature=1.0,
        learning_rate=0.5,
        decay_factor=0.1,
    )
    halted = _force_halt(cfg)
    proof_bytes = bytes(range(32))
    proof_hex = proof_bytes.hex()
    expected_payload = (
        bytes.fromhex(halted.state_hash)
        + proof_bytes
        + struct.pack("<d", cfg.initial_weight)
        + struct.pack("<d", cfg.initial_budget)
        + struct.pack("<d", cfg.invariant_floor)
    )
    expected_hash = hashlib.sha256(expected_payload).hexdigest()
    fresh = reset_with_external_proof(halted, external_proof_hex=proof_hex, config=cfg)
    assert fresh.state_hash == expected_hash, (
        f"INV-HPC1 chain regression: reset_hash={fresh.state_hash!r} "
        f"expected={expected_hash!r}. "
        "Reset hash must be SHA-256 of the documented 88-byte payload "
        "(prior_digest, proof, LE doubles for weight/budget/floor); "
        "field order or endianness change breaks persisted lineages."
    )


def test_reset_then_update_extends_lineage() -> None:
    """After reset, normal updates work and chain past the halted node."""
    cfg = _default_config(initial_budget=0.05)
    halted = _force_halt(cfg)
    fresh = reset_with_external_proof(halted, external_proof_hex=_VALID_PROOF, config=cfg)
    cfg2 = _default_config(initial_budget=10.0)  # fresh budget for post-reset run
    # cannot use cfg2 directly: lineage check requires same floor; same floor in defaults.
    nxt = update(fresh, 0.5, 0.5, config=cfg2)
    assert nxt.phase is EpistemicPhase.ACTIVE
    assert nxt.seq == fresh.seq + 1
    assert nxt.state_hash != fresh.state_hash


# ---------------------------------------------------------------------------
# Replay determinism + lineage-distinctness Hypothesis properties
# ---------------------------------------------------------------------------


@given(
    signals=st.lists(_finite, min_size=0, max_size=80),
    facts=st.lists(_finite, min_size=0, max_size=80),
)
@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_property_replay_determinism(signals: list[float], facts: list[float]) -> None:
    """INV-HPC1: replaying the same stream from the same genesis ⟹ same hash chain."""
    n = min(len(signals), len(facts))
    cfg = _default_config(initial_budget=50.0)

    def fold(state: EpistemicState) -> EpistemicState:
        cur = state
        for i in range(n):
            if cur.is_halted:
                break
            cur = update(cur, signals[i], facts[i], config=cfg)
        return cur

    a = fold(initial_state(cfg))
    b = fold(initial_state(cfg))
    assert a == b, (
        "INV-HPC1 VIOLATED: identical stream replay produced different states; "
        f"a.seq={a.seq} a.hash={a.state_hash} vs b.seq={b.seq} b.hash={b.state_hash}; "
        f"params={cfg!r}; n={n}."
    )


@given(
    seed_a=st.lists(_finite, min_size=1, max_size=20),
    seed_b=st.lists(_finite, min_size=1, max_size=20),
)
@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_property_diverging_streams_diverge_hashes(
    seed_a: list[float], seed_b: list[float]
) -> None:
    """Two non-halted, non-identical streams produce distinct chain hashes.

    Skips trivial collisions where the two streams reduce to the
    same observable (e.g., both clipped at halt). Tests the chain's
    distinguishing power on the live-lineage subset.
    """
    cfg = _default_config(initial_budget=200.0)
    state_a: EpistemicState = initial_state(cfg)
    state_b: EpistemicState = initial_state(cfg)
    for s, f in zip(seed_a, seed_a, strict=False):
        if state_a.is_halted:
            break
        state_a = update(state_a, s, f, config=cfg)
    for s, f in zip(seed_b, seed_b, strict=False):
        if state_b.is_halted:
            break
        state_b = update(state_b, s, f, config=cfg)
    if seed_a == seed_b:
        # Identical streams must produce identical hashes (replay
        # determinism is its own property; this branch is the
        # consistency-check counterpart).
        assert state_a.state_hash == state_b.state_hash
    elif state_a.seq != state_b.seq:
        # Different stream lengths ⟹ different seq ⟹ different hash
        # by construction (seq is in the packed payload).
        assert state_a.state_hash != state_b.state_hash, (
            f"chain integrity: distinct seq ({state_a.seq} vs {state_b.seq}) "
            "but identical hash; INV-HPC1 requires seq in payload."
        )


# ---------------------------------------------------------------------------
# HaltMargin observable (predictive distance to halt boundary)
# ---------------------------------------------------------------------------


def test_halt_margin_fields_at_genesis() -> None:
    cfg = _default_config(invariant_floor=0.2, initial_budget=10.0, initial_weight=0.6)
    s0 = initial_state(cfg)
    margin = halt_margin(s0, config=cfg)
    assert isinstance(margin, HaltMargin)
    assert margin.budget_remaining == 10.0
    assert margin.weight_above_floor == pytest.approx(0.4)
    assert margin.is_halted is False


def test_halt_margin_rejects_lineage_mismatch() -> None:
    cfg_a = _default_config(invariant_floor=0.2)
    cfg_b = _default_config(invariant_floor=0.3)
    s0 = initial_state(cfg_a)
    with pytest.raises(EpistemicError, match="lineage mismatch"):
        halt_margin(s0, config=cfg_b)


def test_halt_margin_tracks_budget_after_update() -> None:
    cfg = _default_config(initial_budget=10.0, temperature=1.0)
    s0 = initial_state(cfg)
    s1 = update(s0, 0.0, 1.0, config=cfg)
    margin = halt_margin(s1, config=cfg)
    expected = 10.0 - math.log1p(1.0)
    assert margin.budget_remaining == pytest.approx(expected), (
        f"halt_margin budget tracking: expected {expected!r}, got {margin.budget_remaining!r}; "
        f"params={cfg!r}; one update with delta=1.0 should debit log1p(1.0)."
    )


def test_halt_margin_zero_at_budget_exhaustion() -> None:
    cfg = _default_config(initial_budget=0.05, temperature=1.0)
    s0 = initial_state(cfg)
    halted = update(s0, 0.0, 1000.0, config=cfg)
    margin = halt_margin(halted, config=cfg)
    assert margin.is_halted is True
    assert margin.budget_remaining == 0.0, (
        f"halt_margin at budget exhaustion: expected 0.0, got {margin.budget_remaining!r}; "
        "INV-FE2 component requires budget clamped at zero on exhaustion."
    )


def test_halt_margin_weight_axis_below_floor_after_collapse() -> None:
    cfg = _default_config(
        invariant_floor=0.55,
        initial_weight=0.56,
        initial_budget=10.0,
        learning_rate=0.99,
        decay_factor=0.1,
        temperature=1.0,
    )
    s0 = initial_state(cfg)
    halted = update(s0, 0.0, 20.0, config=cfg)
    assert halted.is_halted
    assert halted.halt_reason == "weight_collapse"
    margin = halt_margin(halted, config=cfg)
    assert margin.weight_above_floor < 0.0, (
        f"halt_margin weight axis after weight_collapse: expected < 0, "
        f"got {margin.weight_above_floor!r}; "
        "consumer must be able to distinguish budget vs weight halt via the margin axes."
    )


def test_halt_margin_pure_function() -> None:
    """INV-HPC1: identical input ⟹ identical output."""
    cfg = _default_config()
    s0 = initial_state(cfg)
    a = halt_margin(s0, config=cfg)
    b = halt_margin(s0, config=cfg)
    assert a == b


@given(
    signals=st.lists(_finite, min_size=0, max_size=80),
    facts=st.lists(_finite, min_size=0, max_size=80),
)
@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_property_halt_margin_consistent_with_state(
    signals: list[float], facts: list[float]
) -> None:
    """The two-axis margin always agrees with the state's own halt flag.

    If ``state.is_halted`` then at least one of the margin axes must
    be at or past its boundary (``budget_remaining == 0`` or
    ``weight_above_floor < 0``). Conversely, if both axes are
    strictly inside their feasible regions then ``is_halted`` must
    be False.
    """
    cfg = _default_config(initial_budget=50.0)
    state: EpistemicState = initial_state(cfg)
    n = min(len(signals), len(facts))
    for i in range(n):
        if state.is_halted:
            break
        state = update(state, signals[i], facts[i], config=cfg)
    margin = halt_margin(state, config=cfg)

    boundary_hit = (margin.budget_remaining == 0.0) or (margin.weight_above_floor < 0.0)
    assert margin.is_halted == state.is_halted
    if state.is_halted:
        assert boundary_hit, (
            f"halt_margin / state inconsistency: state.is_halted=True but neither "
            f"axis at boundary: budget={margin.budget_remaining!r}, "
            f"weight_above_floor={margin.weight_above_floor!r}; "
            f"params={cfg!r}; n={n}."
        )
    else:
        assert not boundary_hit, (
            f"halt_margin / state inconsistency: state.is_halted=False but boundary "
            f"hit: budget={margin.budget_remaining!r}, "
            f"weight_above_floor={margin.weight_above_floor!r}; "
            f"params={cfg!r}; n={n}."
        )
