# ATTEMPT — CALIB-GRID-001 R1 (estimator-only refinement)

> **Lineage:** refinement attempt **R1** of the closed, pre-registered
> calibration `CALIB-GRID-001` (parent PR #749).
>
> **Frozen ground truth (untouched):** the pre-registration, its five
> acceptance-gate thresholds, the embedded IEEE data, the θ₀
> perturbation, σ, the seeds and the decision rule are the single
> source of truth from PR #749 and are **not** modified by R1. A
> post-data gate retune is a protocol violation; the existing
> `test_preregistration_matches_code` / `test_gate_thresholds_are_frozen_values`
> drift tests stay green.
>
> | Frozen reference | Value |
> |---|---|
> | Pre-registration branch sha | `d170d48afa5066c13edeb40b2c1904b3fd708516` |
> | Parent ledger `ledger_sha256` | `ed8d409b7b222eb053572d6bf9ab6e98c5f4918be1cae384864733a2b4d72aaf` |

## What R1 changed (estimator only)

R1 is an **additive, contract-preserving** change to
`core.kuramoto.coupling_estimator`. The first-order path and every
existing caller/test are untouched; the frozen first-order NEGATIVE
artifact remains bit-identical.

1. **Second-order / inertial design term.** A new swing-aware
   identification path `estimate_swing_coupling` regresses the *full*
   swing identity

   ```
   m_i θ̈_i(t) + d_i θ̇_i(t) = P_i + Σ_{j≠i} (−K_ij) sin(θ_i(t) − θ_j(t))
   ```

   with `(θ̇, θ̈)` from a Savitzky–Golay polynomial differentiator of
   the unwrapped phase. The first-order path folded the unmodelled
   `m_i θ̈_i` into the residual; this path models it explicitly.

2. **Symmetric joint solve (default).** A lossless power-network
   coupling is physically symmetric (PREREGISTRATION § 2; `grid_data`
   builds a symmetric `K`). R1 solves one shared parameter per
   *unordered* edge `K_ij = K_ji` plus one injection `P_i` per node in
   a single global least-squares problem. This is the correct model
   class; it halves the parameter count and **eliminates the
   antisymmetric residual** (parent: `15.9`; R1 noiseless: `0.0`).

3. **Persistent-excitation guard (fail-closed).** The scale-free
   smallest-to-largest singular-value ratio of the standardised global
   design is checked before the solve; a rank-deficient (phase-locked)
   design raises the typed `PersistentExcitationError` instead of
   emitting a misleading `K̂`. This is an instrument-honesty
   invariant, not a tuning knob.

4. **Joint natural-frequency estimate.** `ω_i = P̂_i / d_i` is read
   from the recovered injection of the same swing identity — the
   natural frequency is **not** assumed known and is no longer the
   frequency-median that was blind to phase-locked offsets.

## Pre-committed solver settings (no gate-peeking)

The Savitzky–Golay window/order were fixed **from the signal class,
not from the frozen result**:

- The relative rotor angles of WSCC-9 at scale 8 slew **monotonically**
  to the locked state — there are *no zero-crossings* of the detrended
  relative angle (verified directly). The swing response is
  **over-damped**, not ringing.
- An over-damped monotone transient carries no high-frequency content
  to suppress, so the **minimal-smoothing** SG stencil consistent with
  a degree-4 local fit (the smallest odd window `> polyorder`, i.e.
  `window = 7, polyorder = 4`) is the least-biased derivative. This is
  the analogue of "use the smallest consistent finite-difference
  stencil"; it is dictated by the signal class and is fixed
  independently of any gate value.

## Honest verdict

`verdict = NEGATIVE` (one regime gate now passes, three still fail).
This is the informative outcome of an external-ground-truth
calibration; no promotion language is used. The numeric before→after
table and the next localized defect are in `RESULTS.md`.
