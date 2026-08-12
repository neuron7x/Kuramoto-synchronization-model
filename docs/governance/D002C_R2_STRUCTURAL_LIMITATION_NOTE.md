# D-002C R2 Structural Limitation Note

## Observation

R2 (the false-positive rate rule, "FPR(λ=0) ≤ 0.05") is currently
mechanically satisfied for ALL evaluated λ=0 cells under paired CRN
because `K_precursor == K_baseline` bitwise when λ=0 (by construction
in `d002c_substrates`).

## Mechanism

At λ=0, each substrate's `realize(N=N, lambda_=0.0, seed=s)` produces
`K_precursor` element-wise identical to `K_baseline` (this is the
"null trajectory has no precursor" invariant pinned by the substrate
tests). Under paired CRN, the Kuramoto integrator is invoked twice
with the SAME seed but on different K matrices — except at λ=0 where
the matrices are equal. Therefore both trajectories are bit-identical,
the metric value is identical, the per-seed difference is exactly
zero, `signal_mean = 0`, the bootstrap CI half-width is tiny, and
`signal_over_ci → 0`.

On the canonical D-002C run, R2 measured `FPR = 0.00` across every
swept λ=0 cell of the selected (substrate, metric, N).

## Consequence

R2 in its current implementation has limited evidential strength
as an independent false-positive safeguard: it cannot fail under the
paired-CRN protocol at λ=0 because the construction guarantees zero
signal. R2 still passes the locked rule by formal arithmetic, but
the rule does not differentiate between a real null-respecting
sweep and a broken metric that happens to return identical values.

## What R2 DOES still test

R2 still serves as a contract sanity check:
- if the paired-CRN protocol is broken (substrate/integrator/metric
  inadvertently produces non-zero diff at λ=0), R2 would flag it
- if the metric is non-deterministic in K (returns different values
  on bit-identical inputs), R2 catches it
- if a future implementation introduces accidental λ=0 perturbation,
  R2 catches it

So R2 is NOT a no-op — it is a structural-determinism check. But it
is NOT the false-positive-rate estimator the pre-registration
language implies.

## What R2 DOES NOT test under current implementation

R2 does not measure whether the metric estimator would produce
spurious large-signal values under genuine null noise (the
classical FPR meaning). A genuine null-noise FPR test would need
EITHER:

1. **Unpaired CRN at λ=0**: substrate realised with two different
   seeds for precursor and null evaluation. The seed difference
   injects independent noise; spurious "signals" can arise from
   correlated noise paths. FPR estimate would then be the
   fraction of unpaired-CRN null evaluations where
   `|signal_mean| / CI_half_width > 1`.

2. **Bootstrap-perturbed null**: at λ=0, add a small bounded
   structural perturbation that preserves the null hypothesis
   ("no precursor effect") but breaks the bit-identical
   collapse. The substrate's `realize()` would need a
   `null_perturbation_seed` parameter.

3. **Independent null cohort**: separate the null cohort from
   the precursor cohort by construction (no shared seed),
   accepting the loss of variance reduction from CRN.

None of these are implemented today. The canonical D-002C PASS
remains valid under the locked R1 ∧ R2 ∧ R3 rule, but R2 must be
described in any external write-up as a **structural-determinism
check, not a false-positive-rate estimator**.

## Required follow-up

A future research thread should:

1. Decide which of options (1)–(3) above is methodologically
   appropriate for D-002C-class sweeps.
2. Pre-register the chosen mechanism as a separate rule (R2'),
   not a redefinition of R2 (re-defining a passed rule is
   post-hoc contamination).
3. Implement the new mechanism + a fresh canonical run with the
   redefined acceptance rule applying.

This is **NOT a D-002C launch blocker** — the canonical run
already passed the locked rule. It is a clarity / claim-boundary
issue.

## Claim boundary

The D-002C canonical PASS remains valid under the locked
pre-registered rule. When externally describing the result:

✓ **Allowed:**
- "R2 passes as a structural-determinism check under paired CRN."
- "FPR safeguard is structurally constrained in the current
  paired-CRN implementation; supplementary unpaired-CRN or
  perturbation-based false-positive testing is required for an
  independent FPR claim."

✗ **Forbidden:**
- "D-002C has independently demonstrated FPR ≤ 0.05 under null
  noise."
- "R2 is a false-positive-rate safeguard."
- "False-positive rate has been validated."

## Cross-reference

- `docs/governance/D002C_PREREGISTRATION.yaml` (R2 rule text, locked)
- `docs/governance/D002C_CANONICAL_RUN_REPORT.md` §7.2 (this limitation
  is acknowledged in the canonical run report)
- `research/systemic_risk/d002c_verdict.py::_eval_R2` (current R2
  implementation, unchanged by this note)
