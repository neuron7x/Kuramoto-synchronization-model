# D-002G Degenerate Null Redesign Specification

## Problem

The D-002C attempt-2 canonical run exercised the now-executable
post-sweep null audit (per C2.4-A2 + C2.4-C2 + C2.4-D contract chain)
and FALSIFIED the prior attempt-1 PASS-shape result.

The 9 FAIL cells are exactly the λ=0 cohort. Root cause: under the
locked paired-CRN protocol, at λ=0 the substrate produces
`K_precursor == K_baseline` element-wise (by construction in
`d002c_substrates.realize(lambda_=0.0)`). Therefore the Kuramoto
integrator yields bit-identical trajectories for the "precursor"
and "null" runs, the metric difference is exactly zero per seed,
and the permutation test correctly reports p=1.0 (zero
discriminability).

The null cohort is **degenerate** by construction. This is not a
bug in the runner or in C2.4-A2 — it is a methodological
limitation of the locked null mechanism.

## Why this is not a launch-script defect

- `sweep_runner` ✓ emits valid `NullAuditCellPayload` per cell
- `run_null_audit_all` ✓ consumes real payloads correctly
- `derive_verdict(null_audit_failed=True)` ✓ refuses the verdict
  with explicit notes
- preflight ✓ refuses to launch on null-audit FAIL cells

The contract chain works as designed. The redesign target is the
**null mechanism itself**, not the surrounding infrastructure.

## Scope of D-002G

D-002G replaces or supplements the bit-identical paired-CRN null
at λ=0 so the null cohort has non-trivial discriminability under
permutation testing while preserving the null hypothesis ("no
precursor effect at λ=0").

D-002G is a **research-track** PR. It DOES NOT:
- ❌ retroactively edit `D002C_PREREGISTRATION.yaml`
- ❌ flip the attempt-2 falsification verdict
- ❌ redefine R1, R2, R3 thresholds
- ❌ rescue the attempt-1 PASS narratively

D-002G is the path to a FRESH pre-registration document
(`D002G_PREREGISTRATION.yaml` or similar) under which a NEW
canonical sweep can be run with a non-degenerate null.

## Candidate null mechanisms

### Option 1 — Independent-seed null cohort (recommended starting point)

At λ=0, the "null" cohort uses a DIFFERENT seed for the substrate
realisation than the "precursor" cohort. The Kuramoto trajectories
are no longer bit-identical; under H0 (no precursor effect at
λ=0), the metric difference distribution is symmetric around zero
with non-trivial variance.

Cost: variance reduction from paired CRN is partially lost on the
λ=0 cell only. Other λ values remain paired.

Implementation hook: substrate `realize(N, lambda_, seed)` already
accepts a seed parameter — the runner needs a configuration flag
to pass DIFFERENT seeds for the null-cohort λ=0 evaluation.

### Option 2 — Phase-randomized null

For λ=0 cells, apply Fourier phase randomization to R(t) within the
pre-event window before computing the metric. Preserves the power
spectrum (statistical "shape") but destroys time-domain structure.
The null distribution is non-trivial.

Cost: requires a phase-randomization scaffold around R(t).

### Option 3 — Bounded structural perturbation at λ=0

At λ=0, add a small bounded structural perturbation to K_baseline
(e.g. random edge weight jitter with zero-mean) for the null
cohort only. The perturbation preserves the null hypothesis but
breaks bit-identical collapse.

Cost: requires careful selection of perturbation amplitude to
ensure H0 is genuinely preserved.

### Option 4 — Amplitude-preserving shuffled precursor

For λ=0 cells, generate a "fake precursor" injection with the same
Frobenius norm as a λ>0 precursor, applied to RANDOM edges (not
top-10% curvature edges). The metric should NOT detect this fake
injection. Under H0 the FPR should be ≤ pre-registered threshold.

Cost: requires modification of substrate API to accept random
injection sites.

### Option 5 — Topology-randomised graph null

For Ricci substrate at λ=0: rewire the ER graph preserving degree
sequence but breaking the curvature-coupling correlation. Recompute
the substrate, integrate, evaluate metric.

Cost: substantially more expensive (re-integrates Kuramoto on a
new graph topology).

## Decision deferred

Selection between Options 1–5 is a **research-direction call**
that requires:

- methodological review by Yaroslav (operator)
- compatibility with the C2.4-A2 data contract (NullAuditCellPayload
  schema does not need to change — the values just need to actually
  exhibit discriminability)
- formal pre-registration in a separate protocol document, NOT an
  edit to `D002C_PREREGISTRATION.yaml`

## Implementation prerequisites

D-002G implementation requires:

1. **A FRESH pre-registration document.** This is non-negotiable.
   Editing the locked `D002C_PREREGISTRATION.yaml` after a
   falsification is post-hoc contamination. The new document must
   carry its own content-addressed sha lock.

2. **The chosen null mechanism is documented BEFORE any sweep is
   run.** Same anchor-commit discipline as D-002C: the merge commit
   of the new pre-registration is the lock point.

3. **Acceptance rule** can be inherited from D-002C (R1 ∧ R2 ∧ R3 +
   executable null audit), OR a redesigned R2-B (per
   `D002C_R2_B_SUPPLEMENTARY_NULL_SPEC.md`) can replace R2 for
   D-002G.

## Acceptance criteria for D-002G PR (future)

When D-002G is implemented, the PR must demonstrate:

1. **Non-degenerate null at λ=0** — the per-seed precursor and null
   values are NOT bit-identical (or otherwise non-trivially
   distinguishable).
2. **PASS path under genuine signal** — a known-strong precursor
   (e.g. λ=1.0) produces a per-cell null-audit verdict of PASS
   under the new mechanism.
3. **FAIL path under noise** — a known-null distribution produces
   per-cell null-audit verdict of FAIL only at the pre-registered
   rate (≤ α_bonferroni).
4. **Aggregator emission is content-addressed** — same sha
   round-trip pattern as C2.4-C2.
5. **No locked-YAML edit** — `D002C_PREREGISTRATION.yaml` is
   untouched; a new `D002G_PREREGISTRATION.yaml` (or equivalent)
   exists and is the contract for any D-002G run.

## Priority

P3 in the post-attempt-2 stack:

| Priority | Item | Status |
|---|---|---|
| P0 | Freeze attempt-2 falsification | **this PR** |
| P1 | Confirm append-only ledger | **this PR** |
| P2 | D-002G null mechanism redesign | pending (this spec) |
| P3 | R2-B supplementary null (alternative or additive) | spec at `D002C_R2_B_SUPPLEMENTARY_NULL_SPEC.md` |
| P4 | D-002E metric rehabilitation (tau_onset / phase_lag) | spec at `D002E_METRIC_REHABILITATION_SPEC.md` |
| P5 | #670 Clock DI reliability hardening | pending |

## Claim boundary

D-002G is **research direction + redesign**, not a claim layer.
D-002G does NOT promote any verdict. The path to a synthetic PASS
that survives an executable null audit is:

1. D-002G ships a non-degenerate null mechanism (this spec).
2. A FRESH pre-registration document locks the new acceptance rule.
3. A new canonical sweep runs under that pre-registration.
4. The new sweep's executable null audit MUST report PASS for the
   claim to upgrade.

Until then, the D-002C canonical tier remains
`D002C_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET` per attempt-2.

## Forbidden in D-002G

- ❌ Editing `D002C_PREREGISTRATION.yaml` to relax the null definition.
- ❌ Claiming D-002C PASS based on attempt-1.
- ❌ Removing or reformulating R1, R2, R3 thresholds.
- ❌ Claiming real-data, bank-level, production, or universal
  validation.
- ❌ Treating a non-degenerate null PASS as a re-instatement of
  attempt-1; it is a SEPARATE scientific result.
