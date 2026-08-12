# CTC-FALSIFY-001 · C3 Pre-Registration + Honest Outcome (frozen, pre-data)

C3 replaces the L2 v1 residual estimator (phase-randomization, blind) with a
**time-reversed-surrogate directed Phase-Slope Index** (Nolte 2008;
Schreiber-Schmitz surrogate). Same admissibility bar — only the estimator
changes (no threshold relaxation; that would be a #199-class rescue). SSOT:
`research/ctc_falsify/l2/config_l2.py` (`ESTIMATOR_VERSION = v2_time_reversed_psi`).

## Rationale

Time reversal preserves the power spectrum, autocorrelation, amplitude
distribution and common-drive structure **exactly**, but flips the sign of a
directed phase lag — so a true A→B channel should leave a directed-asymmetry
residual while confound-only signals collapse to ~0.

## Honest reference outcome (NO tuning)

`verdict = INADMISSIBLE_NPLUS_INSITU_BLIND`.

v2 self-validation: N⁺ `residual_z ≈ 0.15` (< 3.0); worst confound
`residual_z ≈ 2.52` (> 1.96). **v2 is also blind by its own pre-registered
gate.** Reported as-is; thresholds untouched.

## Manifestation-vs-boundary elevation (the key C3 finding)

Two **orthogonal** standard estimators now fail the same way:

| estimator | N⁺ z | worst confound z | verdict |
|---|---|---|---|
| v1 phase-randomization PLV-residual | ≈1.6 | ≈2.7 | BLIND |
| v2 time-reversed directed PSI | ≈0.15 | ≈2.52 | BLIND |

Per the manifestation-vs-boundary discipline, before iterating further
estimators we ran a **boundary probe**: a *privileged* mean-gamma-phase-offset
estimator cleanly separates the populations —
N⁺ mean phase offset ≈ −1.38 rad vs N1 common-drive ≈ +0.26 rad;
cross-correlation lag ≈ −251 samples for N⁺.

**Conclusion:** the generative channel is *recoverable in principle*; the
blindness of v1 and v2 is a **manifestation property of the standard CTC
estimands** (PLV-residual, PSI), not a ground-truth defect. This convergent
in-silico blindness is exactly the instrument-level signal the whole
CTC-FALSIFY line exists to surface — but it is in-silico and N=2, so it is
recorded as a **hypothesis**, not a theory claim.

## What this licenses / forbids

- **Forbidden:** lowering the gate, tuning v3 by trial-and-error to "pass".
- **C4 (pre-registered here, pre-data):** ONE principled estimator — the
  mean-gamma-phase-offset *residual* the boundary probe identified — built and
  self-validated. If it clears the gate → estimator admissible →
  `INADMISSIBLE_NO_PAIRED_DATA` (real data still unbound; C5 = bind dataset).
  If it too is blind → STOP estimator iteration (N≥3 convergent failures) and
  elevate to a boundary-conditions writeup: "standard gamma-coherence CTC
  estimands are structurally blind to a known directed channel."

## Honesty invariant

If a principled estimator recovers N⁺ and, on real data (C5), the CTC residual
survives the jointly-matched null — we report **survival**, not spin.

## Verification tags

- FACT: v1 and v2 are blind by their own gates (measured here). confidence=high.
- FACT: the channel is recoverable by a privileged phase-offset estimator
  (boundary probe, asserted in tests). confidence=high.
- INFERENCE: standard CTC estimands are structurally blind here — N=2
  in-silico; hypothesis, not theory. confidence=medium.
- UNKNOWN: real dataset/licence — not touched (C5).

Research line: `ctc_falsify_001` (status OPEN; C3 continues same line).
