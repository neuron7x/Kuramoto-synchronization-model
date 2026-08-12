# D-002C R2-B Supplementary Null Specification

## Problem

R2 in its current form is mechanically satisfied at λ=0 under paired
CRN because `K_precursor == K_baseline` bitwise. Detailed analysis in
`D002C_R2_STRUCTURAL_LIMITATION_NOTE.md`.

R2 should NOT be redefined — that would be post-hoc contamination.
Instead, a supplementary rule **R2-B** is specified here as a
non-trivial false-positive control that complements R2.

## Goal

Provide a real false-positive-rate safeguard that:

1. Does NOT collapse to bit-identical zero-signal at λ=0.
2. Operates on per-cell per-seed paired samples (so it depends on
   C2.4-A2 data contract).
3. Emits a per-cell verdict (PASS / FAIL) consumed by a future
   `derive_verdict` variant.
4. Is pre-registered separately as R2-B in a FRESH protocol
   document, not retrofitted into the locked
   `D002C_PREREGISTRATION.yaml`.

## Candidate null mechanisms (research-track)

Each mechanism breaks the bit-identical collapse at λ=0 while
preserving the null hypothesis "no precursor effect":

### Option 1 — Label-shuffle null

Within each per-cell paired sample of length n_seeds, randomly
permute the (precursor, null) labels with Bernoulli 0.5 per seed.
Recompute `signal_mean`, BCa CI, `signal_over_ci`. The shuffled
distribution under H0 should have `signal_over_ci > 1` at rate
≤ 0.05.

Pros: minimal infrastructure, works with existing data contract once
C2.4-A2 lands.
Cons: still operates on the same Kuramoto trajectory; doesn't probe
metric estimator stability under different noise realisations.

### Option 2 — Seed-permutation null

Resample which seeds belong to the precursor cohort and which to
the null cohort. Under H0 the cohort assignment is exchangeable;
under H1 it is informative. Compute the empirical p-value.

Pros: tests cohort discriminability, not just metric variance.
Cons: requires more per-cell seeds than current n_seeds=20 for
adequate permutation power.

### Option 3 — Phase-randomized null

For each per-cell trajectory, apply Fourier phase randomization
to R(t) within the pre-event window. Phase randomization
preserves the power spectrum (statistical "shape" of the
trajectory) but destroys time-domain structure. Recompute the
metric.

Pros: standard null-testing technique in time-series analysis;
preserves second-order statistics.
Cons: requires explicit FFT scaffold around R(t).

### Option 4 — Topology-preserving graph-randomised null

For Ricci substrate: rewire the ER graph preserving degree
sequence but breaking the curvature-coupling correlation.
Recompute the substrate, integrate, evaluate metric.

Pros: probes whether the precursor mechanism is structurally
embedded in the substrate vs. an artifact of the metric.
Cons: substantially more expensive (re-integrates Kuramoto).

### Option 5 — Amplitude-preserving shuffled precursor null

Generate a "fake precursor" injection with the same Frobenius
norm as the real precursor, applied to RANDOM edges (not top-10%
curvature edges). The metric should NOT detect this fake
injection. Under H0 (fake injection) the FPR should be ≤ 0.05.

Pros: most physically interpretable — tests whether the metric
detects "energy injection" vs. "structurally meaningful
injection".
Cons: requires modification of substrate API to accept random
injection sites.

## Decision deferred

Selection between options 1–5 is a research-direction call that
requires:

- methodological review by a researcher (Yaroslav)
- compatibility check with the C2.4-A2 data contract
- pre-registration in a SEPARATE protocol document
  (not editing `D002C_PREREGISTRATION.yaml`)

## Implementation prerequisites

R2-B implementation requires:

1. **C2.4-A2 merged** — per-seed precursor/null pairs must be
   persisted in the sweep payload (see
   `D002C_NULL_AUDIT_GAP_AND_C2_4_A2_SPEC.md`).
2. **Fresh pre-registration document** — `D002C_V2_PREREGISTRATION.yaml`
   or `D002C_R2B_PREREGISTRATION.yaml`, NOT edits to the locked
   `D002C_PREREGISTRATION.yaml`.
3. **Pre-registered R2-B threshold** — committed BEFORE running
   any R2-B sweep, content-addressed via the same sha-lock
   mechanism as R1/R2/R3.

## Acceptance criteria for R2-B PR (future)

When R2-B is implemented, the PR must demonstrate:

1. R2-B passes a known-clean dataset (proper PASS).
2. R2-B fails an injected-signal-as-null dataset (proper FAIL).
3. R2-B emission is content-addressed (deterministic sha).
4. R2-B verdict is composable into the existing R1+R2+R3 rule
   without modifying the locked rule (i.e., R2-B is ADDITIVE,
   not replacement).

## Priority

P3 in the current stack — AFTER C2.4-A2 + canonical rerun, BEFORE
metric rehabilitation (D-002E):

| Priority | Item |
|---|---|
| P0 | Freeze canonical D-002C result (this PR) |
| P1 | C2.4-A2 per-seed payload data contract |
| P2 | Post-C2.4-A2 canonical rerun |
| **P3** | **R2-B supplementary null (this spec)** |
| P4 | D-002E metric rehabilitation |
| P5 | #670 Clock DI reliability hardening |

## Claim boundary on R2-B

R2-B is **an additional safeguard, not a replacement for R2**.
The locked R2 remains the contract for D-002C as pre-registered.
R2-B is a research thread to address the structural limitation
documented in `D002C_R2_STRUCTURAL_LIMITATION_NOTE.md`. R2-B does
NOT modify or invalidate the canonical D-002C PASS — it
supplements it for future claim strength.
