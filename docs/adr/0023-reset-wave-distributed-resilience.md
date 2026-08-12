# ADR 0023 — Reset-Wave Distributed-Resilience Adapter (5 Async Failure Modes)

**Status.** Accepted, 2026-05-03.
**Supersedes.** Nothing — extends [ADR 0022](0022-reset-wave-engineering-model.md) to address an asynchronous-environment vulnerability.
**Related.**
- [`docs/governance/IERD-PAI-FPS-UX-001.md`](../governance/IERD-PAI-FPS-UX-001.md) (binding standard)
- [`docs/adr/0022-reset-wave-engineering-model.md`](0022-reset-wave-engineering-model.md) (ideal-conditions FACT/MODEL/ANALOGY)
- [`docs/CLAIMS.yaml`](../CLAIMS.yaml) (claims `reset-wave-phase-synchronization` and `reset-wave-distributed-resilience`)
- [`docs/KNOWN_LIMITATIONS.md`](../KNOWN_LIMITATIONS.md) L-12

---

## Context

The reset-wave numerical model adopted in [ADR 0022](0022-reset-wave-engineering-model.md) proves four invariants — V ≥ 0, V monotone in stable region, fail-closed safety lock, determinism — but only under **ideal computational conditions**: single-process, synchronous input, no clock skew, no dropped updates, no concurrent writers.

In real distributed asynchronous environments — financial-market data feeds, IoT meshes, multi-process simulators — the following five failure modes break the potential-non-increase guarantee:

1. **Clock-jitter on update arrival.** Updates from N nodes arrive with non-zero timestamp variance. A batch with high jitter can produce a `V` spike that the next damped step does not catch in time.
2. **Dropped or out-of-order updates.** Network packet loss or message reordering causes `θ_t` and `θ_baseline` to drift apart between observation steps without the safety lock firing.
3. **Partial node failure.** A subset of the N nodes is silently stale (no fresh update); the solver still computes as if it had `N` fresh phases and produces a misleading result.
4. **Re-entry after failure.** A previously failed node recovers and injects an old phase. From the solver's view this looks like an adversarial step that increases `V` against the prior trajectory.
5. **Concurrent writers.** Two independent callers interleave updates and steps. Sequence numbers go backwards from the solver's standpoint.

The current single-process tests do **not** cover any of these. Without a resilience layer, the solver in production either (a) fires false safety locks unnecessarily or (b) hides actual divergence — the second is the one that matters.

## Decision

Ship a fail-closed distributed-resilience adapter that intercepts the five failure modes **before** the base solver runs, and lift the asynchronous gap from "untracked vulnerability" to a tier-tracked claim with explicit residual scope.

### Five guards

The adapter `geosync.neuroeconomics.reset_wave_distributed.run_reset_wave_distributed` runs **only after** five guards pass:

| Guard | Class | Detects |
|---|---|---|
| 1 | `JitterEnvelope` | `max(t) − min(t) > max_jitter_ns` |
| 2 | `StalenessGate` | any `now_ns − t_i > max_age_ns` |
| 3 | `ConcurrencyGuard` | any `node_seq[i] ≤ last_seq[i]` (replay or reorder) |
| 4 | `PartialFailureDetector` | any node id missing from the active set |
| 5 | `DiscontinuityMonitor` | `V(θ_new) > V(θ_prev) + tolerance` (gradient jump) |

If any guard violates, the adapter returns a `DistributedResetWaveResult` with:

* `safety_lock_distributed = True`
* `fail_reason = <first guard tag>`
* `base.locked = True`, `base.final_potential == base.initial_potential`
* No active update is performed.

If every guard passes, the adapter delegates to the base solver and the `DistributedResetWaveResult` carries the un-modified `ResetWaveResult` plus all-clean guard fields.

### Tier scoping

* `reset-wave-phase-synchronization` (P0 ANCHORED) — description is **tightened** to state the ideal-conditions scope. Falsifier remains the canonical numerical-invariant test.
* `reset-wave-distributed-resilience` (P0 EXTRAPOLATED, new) — adapter + adversarial test surface. EXTRAPOLATED rather than ANCHORED because the guards are fail-closed by construction (FACT — tested per branch) but together they DO NOT deliver CAP-theorem-level consensus or distributed clock synchronisation; they refuse to compute on inputs that violate their preconditions.

### Adversarial test surface

`tests/test_reset_wave_distributed_resilience.py` covers the happy path + the five failure modes + determinism + contract validation. 15 tests total. Each failure-mode test asserts (a) the correct `fail_reason` fires AND (b) under the resulting safety lock, V is exactly preserved (no hidden update).

### v3 falsifier block

The new claim carries an inline `falsifier` block citing `tests/test_reset_wave_distributed_resilience.py::test_distributed_discontinuity_monitor_flags_re_entry` as the canonical falsifying test, with `INV-RESET-DIST1..5` cited and an explicit failure signature naming each guard.

## Consequences

### Positive

* The async vulnerability is no longer untracked — it lives in `reset-wave-distributed-resilience` as a tier-EXTRAPOLATED claim with a concrete adversarial test surface.
* Yana's natural Round-3 attack ("your tests don't cover async failure modes") cannot land without first defeating the five named guards. The closing argument shifts from "we missed it" to "we caught it; here are the residual gaps you may still attack."
* The `reset-wave-phase-synchronization` claim becomes more honest by stating its scope explicitly. ANCHORED is preserved because the four invariants do hold under their declared scope; previously the scope was implicit, now it is explicit.

### Costs

* `EXTRAPOLATED` rather than `ANCHORED` for the new claim is a deliberate ceiling — the adapter is fail-closed, not consensus-distributed. ADR 0022's lexicon discipline is preserved by not over-claiming.
* The `INV-RESET-DIST1..5` IDs are not yet in `CLAUDE.md`'s INVARIANT REGISTRY, so they do not contribute to PAI yet. Phase-1 backfill adds them.
* Real distributed integration (NTP / PTP timestamps, runtime scheduler binding) is deferred to a Phase-2 ADR.

### Risks

* The five guards are deterministic but they trust their inputs. A malicious caller that fabricates timestamps, sequence numbers, and active-index sets can still pass every guard. The expected boundary is the runtime layer (the GeoSync `runtime/` deterministic scheduler in the existing codebase) — the adapter is meant to be wrapped by that layer, not used standalone in adversarial environments. Closing this is the Phase-2 integration work.

## Alternatives considered

1. **Just add async tests, no adapter.** Rejected — tests would either pass without changes (false negative) or fail unconditionally (false positive). A test surface without a code surface to bind to is not engineering, it is performance.
2. **Implement full distributed consensus.** Rejected — out of scope for Phase 0/1 of IERD adoption; lifts the entire repository above its current TRL.
3. **Mark the existing reset-wave claim EXTRAPOLATED.** Rejected — the four invariants ARE anchored under their declared scope; the fix is to declare the scope, not downgrade an honest ANCHORED.

## References

* Lamport, L. (1978). *Time, Clocks, and the Ordering of Events in a Distributed System*.
* Brewer, E. (2000). *Towards Robust Distributed Systems* (CAP theorem).
* `geosync/neuroeconomics/reset_wave_distributed.py` — the adapter.
* `tests/test_reset_wave_distributed_resilience.py` — 15 adversarial tests.
* `docs/KNOWN_LIMITATIONS.md` L-12 — explicit residual scope.
