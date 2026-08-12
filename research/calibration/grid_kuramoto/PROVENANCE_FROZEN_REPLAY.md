# Frozen Calibration Replay — Provenance (append-only)

**Status:** append-only epistemic-integrity provenance. This note adds a
*reproduction basis*; it edits no frozen artifact, recomputes no value, and
tunes no threshold.

## Why this exists

The CALIB-GRID pre-registered ledgers (`CALIB-GRID-001`, its `R1` refinement,
and `CALIB-GRID-002`) score a **frozen** experiment. Their reproduction
historically re-ran the live `core.kuramoto.second_order.SecondOrderKuramotoEngine`
to regenerate the phase trajectory. That coupled a byte-frozen scientific
artifact to mutable physics code: a correctness fix to the integrator
(explicit-Euler friction → BBK / semi-implicit velocity Verlet) changed the
*reproduction* of artifacts that the append-only governance contract
(`PREREGISTRATION_AMENDMENT_001`, `SUPERSESSIONS.yaml`) forbids recomputing.

## What changed (forward-only, additive)

1. **Frozen calibration artifacts are historical pre-registered evidence.** The
   `r1/RESULTS.json`, `identifiability/RESULTS.json`, `cg002/RESULTS.json`
   ledgers — and every frozen anchor in the calibration tests — are **byte-
   unchanged**. No recompute, no golden refresh, no threshold tuning.

2. **BBK supersedes the live integrator, forward only.** The damped second-order
   update in `SecondOrderKuramotoEngine` is corrected to the BBK velocity-Verlet
   form (the explicit-Euler friction term dropped the damped map to first order
   and broke the contraction claim, INV-K9/K10). This is the correct path for
   all *new* physics and is proven by the second-order physics tests
   (`tests/unit/physics/test_T18_kuramoto_p1.py`,
   `tests/unit/physics/test_T18b_second_order_stability_guard.py`).

3. **Frozen replay is intentionally insulated from live-integrator evolution.**
   `frozen_replay.py` replays a committed trajectory **snapshot**
   (`frozen_trajectories.npz`) captured at the pre-registration integrator
   state. `calibration.simulate_phases` routes through `obtain_trajectory`,
   which on the default `frozen` basis returns the snapshot and **never calls
   the live engine** for a snapshotted configuration. Identification then runs
   on byte-identical data, so the frozen ledgers reproduce regardless of how the
   live integrator evolves. Enforced by
   `tests/research/calibration/test_frozen_replay_isolation.py`
   (`test_frozen_reproduction_never_calls_live_integrator` sabotages the live
   engine and shows reproduction still succeeds).

4. **Frozen values were not changed.** The noiseless-Frobenius parent anchor
   (≈ 1.0459) and the R1 swing gate (0.0666 ≤ 0.10, PASS) reproduce off the
   snapshot exactly as committed. The live BBK integrator, run on the same
   configuration, would yield different numbers (parent ≈ 1.0232; swing ≈ 0.1135)
   — which is precisely why reproduction is snapshot-isolated rather than live.

## Snapshot basis

`frozen_trajectories.npz` stores the raw engine output `(phases, velocities)`
keyed by a content hash of the trajectory determinants (system, true coupling,
ω, dt, steps, seed, θ₀ perturbation). The key excludes post-integration knobs
(noise σ, keep-fraction, estimator path): the noiseless and noisy regimes share
one raw trajectory; noise and trimming are applied after replay. A configuration
absent from the snapshot falls through to the live engine; a frozen key that
ever drifted would miss the snapshot and surface as a loud reproduction
mismatch, never a silent recompute.
