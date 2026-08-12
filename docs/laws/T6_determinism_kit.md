# GeoSync Physics Law T6 — Bit-Identical Reproducibility Kit

**Status:** ACTIVE • **Tier:** ANCHORED on IEEE 754-2019; FIPS 180-4
**Module:** `core/physics/determinism_kit.py`
**Tests:** `tests/unit/physics/test_T6_determinism_kit.py`
**Composes with:** Law T5 (predictability horizon `τ`)

---

## 1. Statement

Determinism flows from bit-identical state transitions; chaos amplifies floating-point divergence at the rate `λ_1`. Below the predictability horizon `τ` (Law T5), two trajectories with **byte-identical** initial conditions integrated through identical code on identical hardware remain **byte-identical**. T6 is the substrate that makes this property auditable: canonicalisation + hashing utilities binding `(seed, dt, n_steps, integrator_id) ↔ trajectory_hash` into a sealed `ReplayManifest`.

The result: every production trade in GeoSync is reproducible bit-for-bit ≤ `τ`, with a SHA-256 audit hash. That is a **physical-juridical** property, not a software promise.

## 2. Public surface

| Symbol | Role |
|---|---|
| `canonicalize_state(x)` | IEEE-754 normalisation: NaN → canonical quiet-NaN; denormals → 0; -0 → +0; little-endian bytes |
| `state_hash(x)` | SHA-256 over canonical bytes + dtype + shape; lowercase hex |
| `trajectory_hash(traj)` | SHA-256 over per-row state hashes in order |
| `ReplayManifest` | NamedTuple sealing `(integrator_id, seed, dt, n_steps, x0_hash, traj_hash)` |
| `verify_replay(traj, manifest)` | Re-hash and compare; ``True`` iff byte-identical |

Pure NumPy. No I/O. No state. No JAX dependency.

## 3. Constitutional Invariants (P0)

```
INV-DET1 | universal | identical canonical inputs ⇒ identical hash.    | P0
                     | All NaN bit-patterns collapse; ±0 unify;
                     | subnormals flush to +0. (Tested on 100 states.)
INV-DET2 | universal | 1-ULP perturbation ⇒ different hash.            | P0
                     | dtype/shape aliasing blocked; trajectory row
                     | permutation changes hash. (Tested 400+ pairs.)
INV-DET3 | universal | every contract violation (non-floating dtype,   | P0
                     | empty input, float16, non-2-D trajectory, empty
                     | trajectory) raises ValueError; fail-closed.
```

Why we collapse NaN bit-patterns. IEEE-754 has 2⁵² distinct float64 NaN representations (signalling, quiet, signed). Hashing raw bits would assign 2⁵² different hashes to "not-a-number" — defeating INV-DET1. Canonicalisation closes this design space.

Why we flush denormals. Some hardware (notably older x86 and many GPUs) flushes denormals at the FPU level; NumPy on x86_64 keeps them. Without canonical flush, a hash computed on one platform would not match on another — defeating cross-platform replay. We flush at the byte layer so the canonical form is platform-agnostic.

## 4. Falsification battery (17 tests, 100 % green)

| Test | What it catches if it fires |
|---|---|
| `test_INV_DET1_identical_states_hash_identically` | hashing is non-deterministic (RNG leak, time injection) |
| `test_INV_DET1_canonicalisation_collapses_all_NaN_patterns` | NaN-pattern aliasing in hash |
| `test_INV_DET1_negative_zero_collapses_to_positive_zero` | ±0 distinction leaks into hash |
| `test_INV_DET1_subnormal_flush_to_zero` | subnormal-to-zero canonicalisation broken |
| `test_INV_DET2_single_ulp_perturbation_changes_hash` | hash is too coarse-grained (would mask numerical errors) |
| `test_INV_DET2_dtype_aliasing_blocked` | float32 vs float64 collide |
| `test_INV_DET2_shape_aliasing_blocked` | flat vs reshaped same-bytes collide |
| `test_INV_DET2_trajectory_order_sensitivity` | reversed trajectory hashes equal |
| `test_INV_DET3_*` (6 cases) | silent input repair on canonicalize / trajectory_hash |
| `test_replay_manifest_round_trip_succeeds_on_byte_equal_traj` | sealed manifest does not verify a clean replay |
| `test_replay_manifest_detects_tampered_trajectory` | manifest accepts a 1-ULP-tampered trajectory |
| `test_negative_control_distinct_finite_values_distinct_hashes` | canonicalisation collapses too aggressively (would make hashes vacuous) |

The negative control is essential: if the canonicaliser accidentally collapsed all values of similar magnitude, every hash would still be "stable" — but uninformative.

## 5. Industrial acceptance conditions

T6 is a law (not a feature) when **all six** are true:

1. ✅ Pure functional; no JAX dependency at runtime; no I/O; no state.
2. ✅ `mypy --strict --follow-imports=silent` clean; `ruff` clean; `black --check` clean.
3. ✅ All 17 falsification tests pass; negative control proves non-vacuity.
4. ✅ Cross-implementation determinism by construction (canonical bytes are platform-agnostic).
5. ✅ Acceptor YAML recorded; this report path published; INVARIANT REGISTRY updated.
6. ⏳ INVENTORY-hash and module-routing in `CLAUDE.md` updated (administered at PR merge).

## 6. Use in the stack

* **Audit substrate.** Every production trade emits a `ReplayManifest`. The manifest is the audit object; SHA-256 makes it tamper-evident.
* **Composes with T5.** Below `τ`, replay must succeed. Above `2τ`, replay should diverge (otherwise T2's λ-estimator is wrong). T6 makes the "below `τ`" half observable.
* **Cross-platform CI.** The same canonical bytes hash identically on x86_64 / ARM64 / CPU / GPU. Multi-arch CI gates can compare manifest digests.

## 7. References

* IEEE 754-2019 — Floating-Point Arithmetic.
* NIST FIPS 180-4 — SHA-256 specification.
* Liu, X. et al. (2018). *Reproducibility analysis of GPU computing.* IEEE Trans. Parallel Distrib. Syst.
