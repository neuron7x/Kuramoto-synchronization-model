# CTC-FALSIFY-001 · L2 Pre-Registration (frozen, pre-data)

L2 adds the real-data residual machinery to CTC-FALSIFY-001 (L1 merged in
PR #748). It is **not** a test of the CTC theory; it is the fail-closed
instrument that, only after a dataset is bound (C3), can reach
`KILLED_SCOPED` / `SURVIVED_INITIAL`. Constants live only in
`research/ctc_falsify/l2/config_l2.py` (SSOT; `config_hash` pins L1+L2).

## The eight self-audit fixes (wired as gates, not prose)

1. **Standardized residual estimand.** `residual_z = (SFC_obs −
   mean(SFC_surr)) / std(SFC_surr)`; single primary endpoint = fraction of
   pair-directions with `residual_z > Z_GATE`.
2. **Jointly-matched surrogate.** One surrogate matched on rate ∧ power ∧
   common-drive (A fixed, B phase-randomized, B-envelope re-imposed); marginal
   matching forbidden. Mismatch ⇒ `INADMISSIBLE_SURROGATE_MISMATCH`.
3. **Operational positive control.** Known-routing N⁺ must clear
   `NPLUS_RESIDUAL_MIN_Z` while confound-only stays under
   `CONFOUND_RESIDUAL_MAX_Z`; else `INADMISSIBLE_NPLUS_INSITU_BLIND`.
4. **Pre-committed dataset rule / no data pre-bind** ⇒
   `INADMISSIBLE_NO_PAIRED_DATA`.
5. **P-replication gate.** Descriptive coherence↔behavior must replicate on
   the bound dataset, else `INADMISSIBLE_DATASET_UNSUITABLE` (C3).
6. **Multiplicity.** One primary endpoint + Holm for secondaries.
7. **Power.** Pre-registered `MDE_RESIDUAL_Z` + `MIN_SESSIONS`; undershoot ⇒
   `INADMISSIBLE_UNDERPOWERED` (C3).
8. **Symmetric terminal thresholds.** KILLED and SURVIVED use the *same*
   alpha and delta; identical reporting template.

## Reference run (in-silico self-validation, pre-data) — honest outcome

`verdict = INADMISSIBLE_NPLUS_INSITU_BLIND`.

The jointly-matched surrogate matches rate/power to <0.1 % error, **but** the
v1 phase-randomization PLV-residual estimator does **not** clear its own
pre-registered positive-control gate (N⁺ `residual_z ≈ 1.6 < 3.0`;
worst confound `residual_z ≈ 2.7 > 1.96`). Phase randomization destroys the
legitimate channel phase along with the confound, and envelope re-imposition
lets shared-drive structure leak — so the *standard residual-subtraction
approach is itself blind* on the generative ground truth.

This is the designed fail-closed behaviour, **not** a defect to tune away.
Per the contract, thresholds are pre-committed; the estimator is reported
inadmissible. The machine kills its own instrument (cf. L1 amendment A2).

## What this licenses / forbids

- **Forbidden:** lowering `NPLUS_RESIDUAL_MIN_Z`, widening
  `CONFOUND_RESIDUAL_MAX_Z`, or changing the surrogate to make N⁺ "pass" —
  that is post-hoc rescue (#199 class).
- **Required before C3:** a *demonstrably non-blind* residual estimator
  (e.g., a phase-preserving / time-reversed / trial-shuffled surrogate that
  retains channel phase while killing confounds), re-pre-registered, that
  clears self-validation. No real dataset is touched until then.

## Honesty invariant

If, at C3, the CTC residual survives the jointly-matched null with the
estimator non-blind, we report **survival**, not spin — symmetric thresholds,
identical template. The machine is indifferent to the audience.

## Verification tags

- FACT: phase-randomization surrogates degrade legitimate phase structure
  (well known; here measured: N⁺ z≈1.6). confidence=high.
- FACT: L1 generative + L2 surrogate/residual are executable, deterministic,
  mypy-strict clean. confidence=high.
- UNKNOWN: a non-blind estimator design — open problem, not yet pre-registered.
- UNKNOWN: real dataset/licence — not checked, no data touched (C3).

Research line: `ctc_falsify_001` (status OPEN; L2 continues same line).
