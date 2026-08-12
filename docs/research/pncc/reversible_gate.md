# PNCC-C — Reversible Decision Gate

**Module:** `core.physics.reversible_gate`
**Tests:** `tests/unit/physics/test_reversible_gate.py`
**Status:** experimental / **opt-in** behind explicit configuration. Not wired
into the trading pipeline by default.

## 1. Purpose

The Physics-Native Cognitive Kernel (PNCC) introduces an external,
thermodynamically-bounded decision controller. Module **PNCC-C** is the
*reversible decision gate* — every decision path that traverses the gate is
**content-addressable** and **reproducible**:

```
input → state → action → evidence → rollback
```

Each gated decision is recorded as a `DecisionTrace` whose `audit_hash` is the
sha256 over the canonical 5-tuple `(action_id, pre_state_hash,
action_payload, post_state_hash, timestamp_ns)`. Audit hashes are **content
addresses, never object identity / memory address based**.

## 2. Reference

* C. H. Bennett, *"Logical reversibility of computation"*, IBM J. Res. Dev.
  17(6):525–532 (1973). The principle that logically reversible computation
  can in principle be carried out at arbitrarily low energy cost.
* C. H. Bennett, *"The thermodynamics of computation — a review"*,
  Int. J. Theor. Phys. 21:905–940 (1982). Establishes the
  thermodynamic equivalence of logical and physical reversibility.

The PNCC reversible gate operates at the **system-level audit-trail**
layer; it does not claim to operate at the physical reversibility
limit and does not depend on any specific reversible-silicon
demonstration.

## 3. 7 CANONS reference

This module is bound by the GeoSync 7 canons (CLAUDE.md, Section 0 +
INVARIANT REGISTRY):

| Canon                          | How this module observes it |
|--------------------------------|------------------------------|
| **C1 Gradient first**          | Layer-2/3 protector primitive: rollback preserves the gradient state instead of letting an irreversible action collapse it. |
| **C2 No silent fallback**      | Unknown `audit_hash` → `KeyError`. Irreversible action → `ValueError` on `rollback`. NaN / out-of-range score → `ValueError`. |
| **C3 No look-ahead**           | All hashes are computed from caller-supplied bytes only. No `time.time()`, no random nonce inside the gate. |
| **C4 Determinism (INV-HPC1)**  | Same inputs → bit-identical `audit_hash`. Tested over 100 fixed-seed iterations and 50 random tuples. |
| **C5 Finite → finite (INV-HPC2)** | `irreversibility_score` is always a finite float in `[0, 1]`. Tested over 500 random samples plus boundary cases. |
| **C6 Opt-in only**             | Module is not imported anywhere in the production pipeline; it must be wired in by an explicit caller. |
| **C7 Audit-record integrity** | `DecisionTrace` and `RollbackState` are `frozen=True, slots=True` dataclasses — once recorded, fields cannot be mutated. |

## 4. Invariant statement

```
INV-REVERSIBLE-GATE | universal | byte-exact pre-state recovery | P0
```

> For any action with `irreversibility_score <= cfg.irreversibility_threshold`
> (treated as reversible):
>
> ```
> gate.rollback(trace.audit_hash).state_bytes == pre_state
> ```
>
> i.e. byte-exact recovery of the recorded pre-state.

**Falsification battery.** 1000 random reversible actions are pushed through
the gate with random pre-state, post-state, payload, and `score` drawn
uniformly in `[0, threshold]`. Any byte-mismatch between the recovered
`state_bytes` and the original `pre_state` fails the test.

**Test pointer:**
[`tests/unit/physics/test_reversible_gate.py::test_reversible_action_recovers_byte_exact_pre_state`](../../../tests/unit/physics/test_reversible_gate.py).

### Supporting invariants

| ID                  | Type        | Check |
|---------------------|-------------|-------|
| INV-HPC1            | universal   | Seeded reproducibility; same input → bit-identical audit_hash. |
| INV-HPC2            | universal   | `irreversibility_score(...)` is finite ∈ [0, 1] for all finite inputs. |
| INV-REV-FAIL-CLOSED | conditional | Unknown `audit_hash` raises `KeyError`; irreversible rollback raises `ValueError`. |
| INV-REV-NO-GLOBAL   | universal   | Two `ReversibleGate` instances do not share state (no hidden globals). |

## 5. Public API

```python
from core.physics.reversible_gate import (
    DecisionTrace,
    RollbackState,
    ReversibleGateConfig,
    ReversibleGate,
    compute_state_hash,
    compute_audit_hash,
    irreversibility_score,
    canonicalize_payload,
)
```

- `compute_state_hash(state_bytes) -> str` — sha256 with PNCC-C state-domain separator.
- `compute_audit_hash(action_id, pre_state_hash, action_payload, post_state_hash, timestamp_ns) -> str`
  — length-prefixed sha256 over the canonical 5-tuple.
- `irreversibility_score(action_kind, payload_size, side_effects) -> float`
  — pure heuristic in `[0, 1]`, monotone non-decreasing in `side_effects`.
- `canonicalize_payload(payload) -> bytes` — sorted-key minimal JSON
  re-emission; pass-through on non-JSON input.
- `ReversibleGate.gate(...)` — admit a decision, return its `DecisionTrace`.
- `ReversibleGate.rollback(audit_hash)` — recover `RollbackState`.
- `ReversibleGate.is_known(audit_hash)`, `ReversibleGate.trace(audit_hash)`.

## 6. Determinism contract

* No `time.*`, no `random.*`, no `os.urandom` inside the gate.
* Hash inputs are caller-supplied bytes plus a fixed domain separator.
* JSON payloads (when `cfg.canonicalize_json=True`, default) are normalised
  to sorted-key minimal form so semantically equivalent dicts hash to the
  same digest.

## 7. Known limitations

1. **In-memory ledger only.** Persistence (disk / Merkle log) is out of scope
   for this module. Crashing the process loses the ledger.
2. **Hash addressing is sha256, not Merkle root.** A future module
   (`physics_contracts/audit_merkle.py`) is intended to chain `audit_hash`
   values into a Merkle log so the entire decision history can be summarised
   by a single root commitment.
3. **`rollback_payload` is bytes-only.** The gate does not interpret payload
   structure; the caller is responsible for canonical (de)serialisation.
4. **Not thread-safe.** External serialisation (lock or single-writer queue)
   is the caller's responsibility.
5. **Heuristic score.** `irreversibility_score(...)` is a deterministic
   heuristic, not a measurement. Production callers should override it with
   a domain-specific score whenever possible — the gate only requires that
   the supplied score is in `[0, 1]` and reflects true reversibility.
6. **Boolean reversibility.** The `is_reversible` field is a binary
   reduction of a continuous score under `cfg.irreversibility_threshold`.
   Callers that need a graded recovery cost should consult
   `trace.irreversibility_score` directly.

## 8. No-bio-claim disclaimer (verbatim)

> This module audits system-level decision reversibility. It makes no claim
> about human cognition or recovery from cognitive errors. HYP-2
> (reversible-logging reduces error-recovery cost) requires a 90-day
> evidence ledger, see `tacl/evidence_ledger.py`.

## 9. Operational sketch

```python
from core.physics.reversible_gate import ReversibleGate, ReversibleGateConfig

gate = ReversibleGate(ReversibleGateConfig(
    irreversibility_threshold=0.05,
    require_rollback_payload=True,
    fail_on_hash_collision=True,
    canonicalize_json=True,
))

pre = serialize(state)
post = serialize(state.apply(action))
trace = gate.gate(
    action_id="rebalance-2026-04-25T10:00",
    pre_state=pre,
    action_payload=action.to_canonical_bytes(),
    post_state=post,
    irreversibility_score=0.02,   # caller-computed
    timestamp_ns=clock.now_ns(),  # injected; never read from inside the gate
    rollback_payload=pre,
)

# ... if downstream evidence rejects the action ...
if not evidence.accept(trace):
    rb = gate.rollback(trace.audit_hash)
    state = deserialize(rb.state_bytes)  # byte-exact recovery
```
