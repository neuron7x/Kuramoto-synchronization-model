# RESULTS — CALIB-GRID-002 (sha-pinned NEGATIVE artifact)

> **Verdict: `NEGATIVE`.** The integral / weak-form swing identifier
> does **not** close the frozen σ=0.02 / record-length regime the
> differential estimator could not, and it **relocates** the boundary.
> This is the informative outcome of an external-ground-truth
> calibration — **not** a defect of the artifact and **not** a
> "validated" / "breakthrough" result. CALIB-GRID-002 is a new
> pre-registered lineage; the frozen CALIB-GRID-001 / R1 gates, data,
> seeds, σ and θ₀ were not touched.
>
> Source ledger: `cg002/RESULTS.json`
> (`ledger_sha256 = d0f89e24341b0995…`). Pre-registration committed on
> branch `feat/calib-grid-002` off `origin/main`
> `a5e0d533b2201c999b31c792773e858f8da713bf` **before** the run.
> Reproduce: `PYTHONPATH=. python -m research.calibration.grid_kuramoto.run --cg002`.

## The falsifiable claim and its outcome

**Claim (pre-registered):** an integral / weak-form swing identifier
that never double-differentiates the phase recovers signed coupling at
the *same* frozen σ=0.02 / record length where the CALIB-GRID-001 R1
differential estimator provably cannot, and the merged identifiability
front-gate ACCEPTs the σ=0.02 case under the integral form.

**Outcome: FALSIFIED for the noisy regime.** The estimator-class change
improves the noisy Frobenius error by **17.5×** (R1 differential
16.607 → integral 0.947) and improves the noiseless error
(0.0666 → 0.0381, no regression), but it does **not** reach the frozen
≤0.25 target and the front-gate still REFUSEs σ=0.02. The class change
did **not** close what refinement could not; instead it **relocates the
boundary** (see "Where the boundary actually is" below).

## Before → after (tier: MEASURED)

Metric = the pre-registered `cg002.*` gate output. Procedure = WSCC-9
(Anderson & Fouad Ex. 2.6) → `K_true = |V_i||V_j|B_ij` ×8 →
swing-equation trajectory (Störmer-Verlet, published inertia/damping,
frozen θ₀=0.6, seed 42, the *same* `SimConfig` as CALIB-GRID-001) →
estimator → gates. The only change between the two estimator columns is
the estimator **class** (differential double Savitzky–Golay vs
weak/integral test-function projection).

| Quantity | R1 differential | CG002 integral | CG002 gate |
|---|---|---|---|
| noiseless `‖K̂−K‖_F/‖K‖_F` | 0.0666 | **0.0381** | ≤0.10 ✅ PASS |
| noiseless topology F1 | 1.000 | 1.000 | ≥0.95 ✅ PASS |
| noisy `‖K̂−K‖_F/‖K‖_F` (σ=0.02) | 16.607 | **0.9468** | ≤0.25 ❌ FAIL |
| noisy topology F1 (σ=0.02) | 0.800 | 0.800 | ≥0.90 ❌ FAIL |
| theorem-class DCB consistency (noiseless) | — | 0.5000 | ≤0.15 ❌ FAIL |
| front-gate σ=0.02 verdict | REFUSE | **REFUSE** | ACCEPT ❌ FAIL |
| front-gate noiseless verdict | ACCEPT | ACCEPT (R²=0.9997) | — |
| null-battery empirical FPR | — | 0.10 | ≤0.05 ❌ FAIL |

Supporting diagnostics (not gates):

| Quantity | Value |
|---|---|
| weak-design reciprocal condition (noiseless) | 6.44e-05 |
| front-gate R² noiseless / noisy | 0.9997 / 0.0185 |
| null shuffle max corr. with true `K` | 0.829 (1 of 11 draws > 0.8) |
| null flat-coupling off-diagonal dispersion | 0.089 (correctly low) |
| pandapower IEEE-39 `Ybus` parity | **DEFERRED** (see PROVENANCE_002 §4) |

## What the class change did close (numeric deltas, no promotion)

1. **Noisy Frobenius 16.607 → 0.947 (17.5×).** The weak/integral form
   removes the `ω⁴` double-differentiation noise amplification that
   dominated the R1 differential path; integration is a low-pass
   operator (the quadrature of zero-mean noise has variance
   `∝ σ²‖φ‖²Δt` and averages down). The class change is real and
   measurable — it just does not reach the frozen ≤0.25 target.
2. **Noiseless Frobenius 0.0666 → 0.0381 (no regression).** The
   integral form recovers signed coupling at least as well as the
   differential path noiseless; the estimator class is sound.

## Where the boundary actually is (the relocated localization)

CALIB-GRID-001 R1 RESULTS.md attributed the noisy failure to the
**double-differentiation SNR boundary**. CALIB-GRID-002 shows that
attribution is **incomplete**: an estimator that *never* differentiates
the phase still fails at ≈0.95. A direct regressor-level diagnostic on
the frozen σ=0.02 trajectory measures, on the clean coupling regressor
`sin(θ_i−θ_j)` vs the σ=0.02-induced perturbation in the *same*
regressor:

| edge | clean `sin` std | noise-induced std | regressor SNR |
|---|---|---|---|
| (0,1) | 0.01417 | 0.02874 | 0.493 |
| (0,2) | 0.00244 | 0.02873 | 0.085 |
| (1,2) | 0.01611 | 0.02863 | 0.563 |

The coupling signal in the regressor is **below the σ=0.02 measurement
noise** on every edge (SNR < 0.6, and 0.085 on edge (0,2)) **before any
estimator touches the data**. The boundary is therefore a
**regressor-level signal floor at the frozen σ / excitation level**,
which is *class-independent* — no swing identifier (differential,
integral, or otherwise) can recover coupling information the σ=0.02
noise has already destroyed at the frozen over-damped WSCC-9 excitation.
The differential operator made it *worse* (16.6) but is not the cause;
the cause is the frozen experiment's signal-to-noise at this excitation
and record length. This is the corrected, sha-pinned localization.

Two further failing gates localize cleanly:

* **`cg002.noiseless.dcb_consistency` (0.50, ≤0.15).** Same
  pseudo-inverse ill-conditioning the parent R1 `noiseless.critical_coupling`
  hit (≈0.49): the Dörfler–Chertkov–Bullo DC-power-flow prediction goes
  through `L(K̂)⁺` / `B†`, which is ill-conditioned near the locking
  boundary, so the small `K̂` residual amplifies. Localizes to the
  pseudo-inverse propagation, **not** the weak-form estimator class
  (the noiseless Frobenius passes at 0.038).
* **`cg002.null_fpr` (0.10, ≤0.05).** One of 11 topology-preserving
  shuffle draws correlated 0.829 with the true `K`. WSCC-9 has only 3
  unordered edges, so a single permutation can chance-correlate ≈0.8;
  this is a small-graph specificity limitation of the weak-form
  read-out, reported honestly — **not** masked by loosening the gate.
  The flat-coupling placebo is clean (dispersion 0.089).

## What this artifact does *not* claim

It does **not** claim the integral estimator closes the noisy regime
(it does not — 0.947 ≫ 0.25), nor that the GeoSync inverse stack is
validated or calibrated. It claims, at `MEASURED` tier against an exact
external ground truth, that:

* the integral / weak-form estimator class is **sound** noiseless
  (Frobenius 0.0381 ≤ 0.10, F1 = 1.0, front-gate ACCEPT R²=0.9997) and
  improves the noisy error **17.5×** over the R1 differential class;
* the frozen σ=0.02 / record-length regime **does not close** under the
  class change — the falsifiable claim is **FALSIFIED** there;
* the **estimator-class change closed nothing the differential class
  could not**; instead it **relocates the boundary** from
  "double-differentiation" (R1's attribution) to a **class-independent
  regressor-level signal floor at the frozen σ / excitation**, proven
  by a direct regressor SNR measurement (< 0.6 on every edge).

The frozen CALIB-GRID-001 negative artifact stands as the
**differential-class boundary record**; this CALIB-GRID-002 sha-pinned
NEGATIVE stands as the **class-independent regressor-floor boundary
record** and names the next boundary: closing the noisy regime requires
changing the *frozen experiment* (longer record, larger θ₀, lower σ),
which CALIB-GRID-002 is not permitted to do — it is the regressor-floor
boundary, not an estimator-class boundary.
