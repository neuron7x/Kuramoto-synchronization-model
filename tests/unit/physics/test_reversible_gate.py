# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the PNCC-C reversible decision gate.

Invariant under test
--------------------
INV-REVERSIBLE-GATE | universal | byte-exact pre-state recovery | P0
    For any action with ``irreversibility_score <= cfg.irreversibility_threshold``:
    ``gate.rollback(trace.audit_hash).state_bytes == pre_state``.
    Falsification battery: 1000 random reversible actions, any byte
    mismatch → fail.

Supporting invariants
---------------------
INV-HPC1 | universal | seeded reproducibility, bit-identical output | P0
INV-HPC2 | universal | finite inputs → finite outputs, score in [0, 1]  | P0
"""

from __future__ import annotations

import json
import random
from typing import Final

import pytest

from core.physics.reversible_gate import (
    DecisionTrace,
    ReversibleGate,
    ReversibleGateConfig,
    RollbackState,
    canonicalize_payload,
    compute_audit_hash,
    compute_state_hash,
    irreversibility_score,
)

# Falsification battery size for INV-REVERSIBLE-GATE.
_N_RANDOM_ACTIONS: Final[int] = 1000
_FIXED_SEED: Final[int] = 42


def _rand_bytes(rng: random.Random, lo: int = 0, hi: int = 256) -> bytes:
    n = rng.randint(lo, hi)
    return bytes(rng.randint(0, 255) for _ in range(n))


# ---------------------------------------------------------------------------
# Hash determinism (INV-HPC1)
# ---------------------------------------------------------------------------


def test_audit_hash_deterministic() -> None:
    """INV-HPC1: same inputs → same audit_hash, byte-identical."""
    rng = random.Random(_FIXED_SEED)
    seen: list[str] = []
    for _ in range(50):
        action_id = f"act-{rng.randint(0, 10**9)}"
        pre = _rand_bytes(rng, 0, 64)
        post = _rand_bytes(rng, 0, 64)
        payload = _rand_bytes(rng, 0, 64)
        ts = rng.randint(0, 10**18)
        pre_h = compute_state_hash(pre)
        post_h = compute_state_hash(post)
        h1 = compute_audit_hash(action_id, pre_h, payload, post_h, ts)
        h2 = compute_audit_hash(action_id, pre_h, payload, post_h, ts)
        h3 = compute_audit_hash(action_id, pre_h, payload, post_h, ts)
        assert h1 == h2 == h3, (
            f"INV-HPC1 VIOLATED: audit_hash non-deterministic. "
            f"h1={h1!r} h2={h2!r} h3={h3!r}. "
            f"Inputs: action_id={action_id!r}, ts={ts}. "
            f"sha256 must be deterministic for same input. "
            f"Iteration over 50 random tuples, seed={_FIXED_SEED}"
        )
        assert len(h1) == 64, (
            f"INV-HPC1 VIOLATED: audit_hash must be 64-char hex digest, got len={len(h1)}. "
            f"Expected sha256 hex digest length=64. "
            f"Got h1={h1!r}. seed={_FIXED_SEED}, iter sample"
        )
        seen.append(h1)
    # Different inputs should not collide trivially (smoke check on uniqueness).
    assert len(set(seen)) == len(seen), (
        f"INV-HPC1 sanity: 50 random audit hashes had duplicates "
        f"({len(seen) - len(set(seen))}); sha256 collision in random sweep is implausible. "
        f"seed={_FIXED_SEED}"
    )


def test_state_hash_collision_resistance() -> None:
    """INV-HPC1 (universal sweep): distinct inputs → distinct sha256 outputs."""
    rng = random.Random(_FIXED_SEED + 1)
    bag: dict[str, bytes] = {}
    n_samples = 2000
    for _ in range(n_samples):
        b = _rand_bytes(rng, 0, 128)
        h = compute_state_hash(b)
        assert isinstance(h, str), (
            f"compute_state_hash must return str, got {type(h)!r}. "
            f"Input len={len(b)}. seed={_FIXED_SEED + 1}"
        )
        assert len(h) == 64, (
            f"compute_state_hash output length VIOLATED: expected 64 hex chars, got {len(h)}. "
            f"Input len={len(b)}, h={h!r}, seed={_FIXED_SEED + 1}"
        )
        if h in bag:
            assert bag[h] == b, (
                f"sha256 COLLISION on distinct inputs (cryptographic break — should not happen). "
                f"h={h!r}, prior={bag[h]!r}, new={b!r}. seed={_FIXED_SEED + 1}"
            )
        bag[h] = b
    assert len(bag) >= n_samples // 2, (
        f"compute_state_hash: too few unique digests over {n_samples} samples (got {len(bag)}). "
        f"sha256 over random bytes should be ~1:1. seed={_FIXED_SEED + 1}"
    )


# ---------------------------------------------------------------------------
# Core invariant: byte-exact rollback for reversible actions (INV-REVERSIBLE-GATE)
# ---------------------------------------------------------------------------


def test_reversible_action_recovers_byte_exact_pre_state() -> None:
    """INV-REVERSIBLE-GATE (P0, universal): 1000 random reversible actions,
    byte-exact pre-state recovery, any mismatch fails.
    """
    rng = random.Random(_FIXED_SEED)
    cfg = ReversibleGateConfig(
        irreversibility_threshold=0.10,
        require_rollback_payload=False,  # exercise implicit pre-state-as-rollback path
    )
    gate = ReversibleGate(cfg)
    mismatches: list[tuple[int, bytes, bytes]] = []
    for i in range(_N_RANDOM_ACTIONS):
        pre = _rand_bytes(rng, 0, 256)
        post = _rand_bytes(rng, 0, 256)
        payload = _rand_bytes(rng, 0, 64)
        # Force reversible regime: score in [0, threshold]
        score = rng.uniform(0.0, cfg.irreversibility_threshold)
        ts = i  # monotone but the contract does not require monotone
        trace = gate.gate(
            action_id=f"act-{i}",
            pre_state=pre,
            action_payload=payload,
            post_state=post,
            irreversibility_score=score,
            timestamp_ns=ts,
        )
        assert trace.is_reversible, (
            f"INV-REVERSIBLE-GATE setup VIOLATED: trace.is_reversible=False at i={i} "
            f"with score={score:.6f}, threshold={cfg.irreversibility_threshold:.6f}. "
            f"Expected reversible. "
            f"seed={_FIXED_SEED}, N={_N_RANDOM_ACTIONS}, action_id=act-{i}"
        )
        rb = gate.rollback(trace.audit_hash)
        if rb.state_bytes != pre:
            mismatches.append((i, pre, rb.state_bytes))

    assert not mismatches, (
        f"INV-REVERSIBLE-GATE VIOLATED: {len(mismatches)}/{_N_RANDOM_ACTIONS} "
        f"reversible rollbacks did NOT recover byte-exact pre-state. "
        f"Expected rb.state_bytes == pre for all. "
        f"First mismatch: i={mismatches[0][0]}, "
        f"pre_len={len(mismatches[0][1])}, rb_len={len(mismatches[0][2])}. "
        f"seed={_FIXED_SEED}, N={_N_RANDOM_ACTIONS}, threshold=0.10"
    )


def test_reversible_action_explicit_rollback_recovers_supplied_payload() -> None:
    """INV-REVERSIBLE-GATE: when caller supplies rollback_payload, that exact
    bytes blob (not pre_state) is what rollback returns.

    This locks the contract that the gate stores what the caller passed,
    not what it inferred — preventing silent substitution.
    """
    rng = random.Random(_FIXED_SEED + 2)
    cfg = ReversibleGateConfig(
        irreversibility_threshold=0.10,
        require_rollback_payload=True,
    )
    gate = ReversibleGate(cfg)
    for i in range(200):
        pre = _rand_bytes(rng, 0, 64)
        post = _rand_bytes(rng, 0, 64)
        payload = _rand_bytes(rng, 0, 64)
        explicit_rb = _rand_bytes(rng, 0, 64)
        trace = gate.gate(
            action_id=f"explicit-{i}",
            pre_state=pre,
            action_payload=payload,
            post_state=post,
            irreversibility_score=0.0,
            timestamp_ns=i,
            rollback_payload=explicit_rb,
        )
        rb = gate.rollback(trace.audit_hash)
        assert rb.state_bytes == explicit_rb, (
            f"INV-REVERSIBLE-GATE VIOLATED: explicit rollback_payload not preserved at i={i}. "
            f"Expected supplied bytes (len={len(explicit_rb)}), "
            f"got len={len(rb.state_bytes)}. "
            f"seed={_FIXED_SEED + 2}, action_id=explicit-{i}"
        )
        assert rb.audit_hash == trace.audit_hash, (
            f"RollbackState.audit_hash mismatch: rb={rb.audit_hash!r} trace={trace.audit_hash!r}. "
            f"At i={i}, seed={_FIXED_SEED + 2}, action_id=explicit-{i}"
        )
        assert rb.state_hash == compute_state_hash(explicit_rb), (
            f"RollbackState.state_hash inconsistent with state_bytes. "
            f"rb.state_hash={rb.state_hash!r}, "
            f"recomputed={compute_state_hash(explicit_rb)!r}. "
            f"At i={i}, seed={_FIXED_SEED + 2}, action_id=explicit-{i}"
        )


# ---------------------------------------------------------------------------
# Irreversible actions
# ---------------------------------------------------------------------------


def test_irreversible_action_has_no_rollback_payload() -> None:
    """Universal: irreversible actions carry rollback_payload=None and
    rollback() raises (no silent fallback)."""
    cfg = ReversibleGateConfig(irreversibility_threshold=0.05)
    gate = ReversibleGate(cfg)
    rng = random.Random(_FIXED_SEED + 3)
    n_checked = 0
    for i in range(100):
        score = rng.uniform(0.06, 1.0)  # strictly above threshold
        trace = gate.gate(
            action_id=f"irr-{i}",
            pre_state=_rand_bytes(rng, 0, 32),
            action_payload=_rand_bytes(rng, 0, 32),
            post_state=_rand_bytes(rng, 0, 32),
            irreversibility_score=score,
            timestamp_ns=i,
            rollback_payload=b"caller-thinks-they-can-rollback",  # must be ignored
        )
        assert not trace.is_reversible, (
            f"Irreversible setup VIOLATED at i={i}: expected is_reversible=False, got True. "
            f"score={score:.6f}, threshold={cfg.irreversibility_threshold:.6f}. "
            f"action_id=irr-{i}, seed={_FIXED_SEED + 3}"
        )
        assert trace.rollback_payload is None, (
            f"Irreversible trace has non-None rollback_payload at i={i}. "
            f"Expected None (no false promise of recovery). "
            f"Got {trace.rollback_payload!r}. "
            f"score={score:.6f}, action_id=irr-{i}, seed={_FIXED_SEED + 3}"
        )
        with pytest.raises(ValueError, match="irreversible"):
            gate.rollback(trace.audit_hash)
        n_checked += 1
    assert n_checked == 100, (
        f"Test loop did not run 100 iterations (got {n_checked}). "
        f"seed={_FIXED_SEED + 3}, threshold={cfg.irreversibility_threshold}"
    )


def test_rollback_unknown_hash_raises() -> None:
    """Universal (fail-closed): rollback of an unknown audit_hash → KeyError."""
    gate = ReversibleGate()
    bogus_hashes = [
        "0" * 64,
        "f" * 64,
        "deadbeef" * 8,
        "a1b2c3d4" * 8,
    ]
    for h in bogus_hashes:
        with pytest.raises(KeyError, match="unknown audit_hash"):
            gate.rollback(h)
    with pytest.raises(TypeError, match="must be str"):
        gate.rollback(b"not a string")  # type: ignore[arg-type]
    # Also: trace() must fail-closed identically.
    for h in bogus_hashes:
        with pytest.raises(KeyError, match="unknown audit_hash"):
            gate.trace(h)


# ---------------------------------------------------------------------------
# irreversibility_score helper
# ---------------------------------------------------------------------------


def test_irreversibility_score_monotone_in_side_effects() -> None:
    """Qualitative: ``side_effects`` is a non-decreasing argument."""
    rng = random.Random(_FIXED_SEED + 4)
    kinds = ["noop", "read", "compute", "write", "submit", "broadcast", "trade", "unknown_kind_x"]
    violations: list[tuple[str, int, int, float, float]] = []
    for _ in range(200):
        kind = rng.choice(kinds)
        payload_size = rng.randint(0, 4096)
        prev = -1.0
        prev_se = -1
        for se in [0, 1, 2, 5, 10, 50, 100, 1000]:
            s = irreversibility_score(kind, payload_size, se)
            if s < prev - 1e-12:
                violations.append((kind, payload_size, se, prev, s))
            prev = s
            prev_se = se
        assert prev_se == 1000, (
            f"loop sentinel: expected last side_effects=1000, got {prev_se}. "
            f"kind={kind!r}, payload_size={payload_size}"
        )
    assert not violations, (
        f"irreversibility_score MONOTONICITY VIOLATED in {len(violations)} cases; "
        f"score must be non-decreasing in side_effects. "
        f"First: kind={violations[0][0]!r}, payload={violations[0][1]}, "
        f"se={violations[0][2]}, prev={violations[0][3]:.6f}, now={violations[0][4]:.6f}. "
        f"seed={_FIXED_SEED + 4}"
    )


def test_irreversibility_score_in_unit_interval() -> None:
    """INV-HPC2 + universal: score ∈ [0, 1] for all reasonable finite inputs."""
    rng = random.Random(_FIXED_SEED + 5)
    kinds = [
        "noop",
        "read",
        "compute",
        "log",
        "snapshot",
        "write",
        "submit",
        "cancel",
        "broadcast",
        "external_io",
        "trade",
        "settlement",
        "this_kind_is_unknown",
    ]
    out_of_range: list[tuple[str, int, int, float]] = []
    nan_or_inf: list[tuple[str, int, int, float]] = []
    for _ in range(500):
        kind = rng.choice(kinds)
        payload_size = rng.randint(0, 1_000_000)
        side_effects = rng.randint(0, 100_000)
        s = irreversibility_score(kind, payload_size, side_effects)
        if s != s or s in (float("inf"), float("-inf")):
            nan_or_inf.append((kind, payload_size, side_effects, s))
        if s < 0.0 or s > 1.0:
            out_of_range.append((kind, payload_size, side_effects, s))
    assert not nan_or_inf, (
        f"INV-HPC2 VIOLATED: irreversibility_score returned NaN/Inf for finite inputs. "
        f"{len(nan_or_inf)} bad samples, first: {nan_or_inf[0]!r}. "
        f"seed={_FIXED_SEED + 5}, kinds={kinds!r}"
    )
    assert not out_of_range, (
        f"irreversibility_score range VIOLATED: {len(out_of_range)} samples outside [0,1]. "
        f"First: {out_of_range[0]!r}. "
        f"seed={_FIXED_SEED + 5}"
    )

    # Boundary: pure noop with no payload, no side effects → exactly 0.0.
    assert irreversibility_score("noop", 0, 0) == 0.0, (
        f"Boundary VIOLATED: irreversibility_score('noop',0,0) must be exactly 0.0, "
        f"got {irreversibility_score('noop', 0, 0)!r}. "
        f"Reason: pure read-only / zero-payload / zero-side-effect must score 0."
    )
    # Boundary: settlement with high payload + side effects → near 1.
    high = irreversibility_score("settlement", 1_000_000, 1_000_000)
    high_in_unit_interval = 0.0 <= high <= 1.0
    assert high_in_unit_interval, (
        f"INV-HPC2 boundary VIOLATED: high-impact settlement score outside the "
        f"unit interval [0, 1] for finite inputs. "
        f"Got high={high!r}; payload_size=1_000_000, side_effects=1_000_000."
    )
    assert high >= 0.99, (
        f"Boundary VIOLATED: settlement+huge-payload+huge-side-effects must approach 1, "
        f"got {high:.6f}. The combiner saturates only correctly near full impact."
    )


# ---------------------------------------------------------------------------
# Canonical JSON
# ---------------------------------------------------------------------------


def test_canonical_json_roundtrip_stable() -> None:
    """Algebraic: semantically equal JSON payloads → same audit_hash."""
    p1 = json.dumps({"b": 2, "a": 1, "c": [3, 1, 2]}).encode("utf-8")
    p2 = json.dumps({"a": 1, "c": [3, 1, 2], "b": 2}, indent=2, separators=(", ", ": ")).encode(
        "utf-8"
    )
    p3 = b'{"c":[3,1,2],"a":1,"b":2}'  # no whitespace, different order
    canon1 = canonicalize_payload(p1)
    canon2 = canonicalize_payload(p2)
    canon3 = canonicalize_payload(p3)
    assert canon1 == canon2 == canon3, (
        f"canonicalize_payload VIOLATED: equivalent JSON payloads canonicalised differently. "
        f"canon1={canon1!r}, canon2={canon2!r}, canon3={canon3!r}. "
        f"Expected all three to collapse to the same sorted-key minimal form."
    )

    # Now run through the gate with canonicalize_json=True and check audit_hash collapse.
    cfg = ReversibleGateConfig(
        canonicalize_json=True, irreversibility_threshold=0.5, require_rollback_payload=False
    )
    gate = ReversibleGate(cfg)
    pre = b"pre"
    post = b"post"
    t1 = gate.gate("a", pre, p1, post, 0.0, 100)
    t2 = gate.gate("a", pre, p2, post, 0.0, 100)
    t3 = gate.gate("a", pre, p3, post, 0.0, 100)
    assert t1.audit_hash == t2.audit_hash == t3.audit_hash, (
        f"canonicalize_json VIOLATED at gate level: equivalent JSON payloads "
        f"produced different audit_hash. "
        f"t1={t1.audit_hash!r}, t2={t2.audit_hash!r}, t3={t3.audit_hash!r}. "
        f"All three traces should be merged (idempotent re-admission)."
    )

    # And: when canonicalize_json=False, different bytes should produce different hashes.
    cfg2 = ReversibleGateConfig(
        canonicalize_json=False, irreversibility_threshold=0.5, require_rollback_payload=False
    )
    gate2 = ReversibleGate(cfg2)
    u1 = gate2.gate("a", pre, p1, post, 0.0, 100)
    u3 = gate2.gate("a", pre, p3, post, 0.0, 100)
    assert u1.audit_hash != u3.audit_hash, (
        f"Without canonicalisation, byte-distinct payloads must hash distinctly; "
        f"u1={u1.audit_hash!r} u3={u3.audit_hash!r}. "
        f"This locks canonicalize_json semantics to actually do something."
    )


# ---------------------------------------------------------------------------
# Determinism (INV-HPC1) + isolation
# ---------------------------------------------------------------------------


def test_gate_deterministic_under_fixed_seed() -> None:
    """INV-HPC1: two identical fixed-seed runs produce identical audit_hash sequences."""

    def _run() -> list[str]:
        rng = random.Random(_FIXED_SEED)
        gate = ReversibleGate(
            ReversibleGateConfig(irreversibility_threshold=0.10, require_rollback_payload=False)
        )
        out: list[str] = []
        for i in range(100):
            pre = _rand_bytes(rng, 0, 64)
            post = _rand_bytes(rng, 0, 64)
            payload = _rand_bytes(rng, 0, 64)
            score = rng.uniform(0.0, 0.1)
            tr = gate.gate(f"a-{i}", pre, payload, post, score, i)
            out.append(tr.audit_hash)
        return out

    seq1 = _run()
    seq2 = _run()
    assert seq1 == seq2, (
        f"INV-HPC1 VIOLATED: seeded run produced different audit_hash sequences. "
        f"len(seq1)={len(seq1)}, len(seq2)={len(seq2)}. "
        f"First diff index: "
        f"{next((i for i, (a, b) in enumerate(zip(seq1, seq2)) if a != b), 'none')}. "
        f"seed={_FIXED_SEED}"
    )
    assert len(set(seq1)) == len(seq1), (
        f"INV-HPC1 sanity: 100 random hashes had {len(seq1) - len(set(seq1))} duplicates; "
        f"sha256 collision in random sweep is implausible. seed={_FIXED_SEED}"
    )


def test_gate_does_not_share_state_across_instances() -> None:
    """Universal (no hidden global state): two gates are mutually invisible."""
    g1 = ReversibleGate()
    g2 = ReversibleGate()
    pre = b"pre-state"
    post = b"post-state"
    t = g1.gate("act-shared", pre, b"payload", post, 0.0, 1, rollback_payload=pre)
    assert g1.is_known(t.audit_hash), (
        f"g1 forgot trace {t.audit_hash!r} after writing it. "
        f"Ledger size after write: {len(g1._traces) if hasattr(g1, '_traces') else 'unknown'}"
    )
    assert not g2.is_known(t.audit_hash), (
        f"INSTANCE LEAK: g2 sees a trace written to g1 (audit_hash={t.audit_hash!r}). "
        f"This implies hidden global state — explicitly forbidden."
    )
    with pytest.raises(KeyError):
        g2.rollback(t.audit_hash)
    with pytest.raises(KeyError):
        g2.trace(t.audit_hash)
    # And state is symmetric: write into g2, g1 must not see it.
    t2 = g2.gate("act-shared-2", pre, b"payload-2", post, 0.0, 2, rollback_payload=pre)
    assert g2.is_known(t2.audit_hash)
    leaked_into_g1 = g1.is_known(t2.audit_hash)
    assert not leaked_into_g1, (
        f"INSTANCE LEAK (reverse): g1 unexpectedly sees trace {t2.audit_hash!r} "
        f"that was written to g2; this would imply hidden global ledger state, "
        f"which the contract forbids."
    )


# ---------------------------------------------------------------------------
# Conditional / boundary contracts
# ---------------------------------------------------------------------------


def test_rollback_payload_required_when_reversible() -> None:
    """Conditional: cfg.require_rollback_payload=True + reversible + None payload → ValueError."""
    cfg = ReversibleGateConfig(irreversibility_threshold=0.10, require_rollback_payload=True)
    gate = ReversibleGate(cfg)
    with pytest.raises(ValueError, match="require_rollback_payload"):
        gate.gate(
            action_id="needs-rb",
            pre_state=b"x",
            action_payload=b"p",
            post_state=b"y",
            irreversibility_score=0.0,
            timestamp_ns=1,
            rollback_payload=None,
        )
    # Same call with explicit payload must succeed.
    trace = gate.gate(
        action_id="needs-rb",
        pre_state=b"x",
        action_payload=b"p",
        post_state=b"y",
        irreversibility_score=0.0,
        timestamp_ns=1,
        rollback_payload=b"rb-explicit",
    )
    assert trace.rollback_payload == b"rb-explicit"
    rb = gate.rollback(trace.audit_hash)
    assert rb.state_bytes == b"rb-explicit"

    # And: when require_rollback_payload=False, omission auto-fills with pre_state.
    cfg2 = ReversibleGateConfig(irreversibility_threshold=0.10, require_rollback_payload=False)
    gate2 = ReversibleGate(cfg2)
    trace2 = gate2.gate(
        action_id="auto-rb",
        pre_state=b"PRE",
        action_payload=b"P",
        post_state=b"POST",
        irreversibility_score=0.0,
        timestamp_ns=1,
        rollback_payload=None,
    )
    assert trace2.rollback_payload == b"PRE", (
        f"With require_rollback_payload=False the gate must default to pre_state. "
        f"Got {trace2.rollback_payload!r}, expected b'PRE'."
    )


def test_pre_state_below_threshold_treated_reversible() -> None:
    """Algebraic boundary: score == threshold → reversible (boundary inclusive)."""
    cfg = ReversibleGateConfig(irreversibility_threshold=0.05)
    gate = ReversibleGate(cfg)
    # score == threshold → reversible by ``<=``
    trace_eq = gate.gate(
        action_id="boundary-eq",
        pre_state=b"P",
        action_payload=b"a",
        post_state=b"Q",
        irreversibility_score=0.05,
        timestamp_ns=1,
        rollback_payload=b"P",
    )
    assert trace_eq.is_reversible, (
        f"Boundary VIOLATED: score==threshold must be REVERSIBLE (inclusive ≤). "
        f"Got is_reversible={trace_eq.is_reversible}, score={trace_eq.irreversibility_score}, "
        f"threshold={cfg.irreversibility_threshold}"
    )
    # score < threshold → reversible
    trace_lt = gate.gate(
        action_id="boundary-lt",
        pre_state=b"P",
        action_payload=b"a",
        post_state=b"Q",
        irreversibility_score=0.04999,
        timestamp_ns=2,
        rollback_payload=b"P",
    )
    assert trace_lt.is_reversible
    # score > threshold (epsilon above) → irreversible
    trace_gt = gate.gate(
        action_id="boundary-gt",
        pre_state=b"P",
        action_payload=b"a",
        post_state=b"Q",
        irreversibility_score=0.05 + 1e-9,
        timestamp_ns=3,
    )
    assert not trace_gt.is_reversible, (
        f"Boundary VIOLATED: score>threshold must be IRREVERSIBLE. "
        f"Got is_reversible={trace_gt.is_reversible}, score={trace_gt.irreversibility_score}, "
        f"threshold={cfg.irreversibility_threshold}"
    )


# ---------------------------------------------------------------------------
# Idempotency + collision handling
# ---------------------------------------------------------------------------


def test_gate_idempotent_same_inputs_same_trace() -> None:
    """Re-admitting an identical trace returns the same DecisionTrace, no error."""
    gate = ReversibleGate()
    t1 = gate.gate("idem", b"P", b"p", b"Q", 0.0, 1, rollback_payload=b"P")
    t2 = gate.gate("idem", b"P", b"p", b"Q", 0.0, 1, rollback_payload=b"P")
    assert t1.audit_hash == t2.audit_hash, (
        f"Idempotency VIOLATED: identical inputs produced different audit_hash. "
        f"t1={t1.audit_hash!r}, t2={t2.audit_hash!r}"
    )
    same_trace = t1 is t2 or t1 == t2
    assert same_trace, (
        f"Idempotency VIOLATED: re-admitting an identical trace produced an "
        f"unequal DecisionTrace; the gate must return the existing record. "
        f"t1={t1!r}, t2={t2!r}"
    )


# ---------------------------------------------------------------------------
# Type safety / fail-closed surface
# ---------------------------------------------------------------------------


def test_gate_rejects_invalid_inputs_fail_closed() -> None:
    """Universal fail-closed: bad types/values raise, never silently accepted."""
    gate = ReversibleGate()
    with pytest.raises(TypeError):
        gate.gate(123, b"p", b"a", b"q", 0.0, 0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        gate.gate("a", "not-bytes", b"a", b"q", 0.0, 0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        gate.gate("a", b"p", b"a", b"q", "high", 0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="NaN"):
        gate.gate("a", b"p", b"a", b"q", float("nan"), 0)
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        gate.gate("a", b"p", b"a", b"q", 1.5, 0)
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        gate.gate("a", b"p", b"a", b"q", -0.01, 0)
    with pytest.raises(ValueError, match=">= 0"):
        gate.gate("a", b"p", b"a", b"q", 0.0, -1)
    with pytest.raises(TypeError):
        gate.gate("a", b"p", b"a", b"q", 0.0, 0, rollback_payload="rb")  # type: ignore[arg-type]


def test_decision_trace_is_immutable() -> None:
    """Frozen dataclass: cannot mutate trace fields (audit-record integrity)."""
    gate = ReversibleGate()
    t = gate.gate("im", b"P", b"a", b"Q", 0.0, 1, rollback_payload=b"P")
    with pytest.raises((AttributeError, TypeError, Exception)):
        t.action_id = "tampered"  # type: ignore[misc]
    # Public types we expect to exist + be frozen
    assert isinstance(t, DecisionTrace)
    rb = gate.rollback(t.audit_hash)
    assert isinstance(rb, RollbackState)
