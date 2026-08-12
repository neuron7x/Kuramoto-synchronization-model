# D-002I — Investigation rationale

Date: 2026-05-14
Parent canonical run: D-002H (`PR #691`, merge sha `250d8069d16ecabdb49b5a20b7cf1d622eddc925`)
Parent verdict: `REFUSED_NULL_AUDIT_FAIL_D002H`
Parent null-audit aggregate: 42 / 54 audited cells FAIL on ricci_flow under M1 ∪ M3.

---

## Section 1 — Why D-002I exists

The D-002H canonical sweep delivered a truthful REFUSED verdict. The
permutation null audit aggregated FAIL across 42/54 audited cells on
ricci_flow under M1 ∪ M3 null mechanisms. The D-002H prereg lock,
the 7-gate authorisation chain (A..G), and the R2-B inapplicability
scope clarification are all preserved as merged artifacts.

A REFUSED canonical verdict invites exactly one disciplined response:
investigate WHY the audit failed, and do so under a pre-registered
falsification protocol that locks the hypotheses BEFORE any
investigation code runs. D-002I is that pre-registration.

D-002I does NOT propose a mechanism change. D-002I does NOT propose
a new canonical sweep. D-002I does NOT amend D-002H or rescue any
prior lineage letter. D-002I scopes itself to four falsifiable
hypotheses about the failure axes, each tested in a separate
downstream PR (D-002I-P1/H1..H4) under a pre-committed protocol.

---

## Section 2 — Why post-hoc tuning is forbidden

The most natural human response to a permutation null audit FAIL is
"try a different seed offset and see what happens". This is exactly
the failure mode pre-registration exists to prevent. If a sweep is
re-run under a tuned parameter chosen AFTER the failure was observed,
the resulting PASS is not falsification evidence — it is parameter
search disguised as science.

D-002I therefore commits, before any code edit, to:

- the exact parameter sets each hypothesis will be evaluated on
  (`hypothesis_parameter_sets` in the prereg YAML);
- the exact support criterion (a binary FAIL -> PASS flip on the
  aggregate verdict, or the equivalent for H_I4);
- the exact refutation criterion;
- the boundary that each result is scoped to a single hypothesis
  and does NOT retroactively flip the D-002H REFUSED canonical
  verdict.

Any post-merge edit to D-002I constitutes a fresh D-002K
pre-registration, not a patch.

---

## Section 3 — Why each hypothesis is scoped

Four hypotheses isolate four distinct candidate failure axes:

- **H_I1** isolates the M1 mechanism's seed offset. Scope: M1 only.
  Does NOT touch M3, signal magnitude, or Bonferroni correction.
- **H_I2** isolates the M3 generator's marginal tolerance. Scope: M3
  only. Does NOT touch M1, signal magnitude, or Bonferroni.
- **H_I3** isolates the signal magnitude. Scope: interpretation
  only — substrate code stays locked; the runner parametrises
  lambda externally.
- **H_I4** isolates the Bonferroni denominator. Scope: re-verdict
  against the existing sweep capsule; does NOT re-run any sweep.

A REFUTED outcome on a single hypothesis is informative on that axis
alone. A SUPPORTED outcome on a single hypothesis names a candidate
failure axis but does NOT itself authorise a canonical sweep — that
requires a separate D-002J pre-registration designed against the
identified axis.

---

## Section 4 — What claims become possible per outcome path

### 4.1 All 4 REFUTED

Permitted claims:

- "D-002H REFUSED is structural at the tested signal magnitude
  on ricci_flow under M1 ∪ M3."
- "M1 seed offset, M3 marginal tolerance, signal magnitude, and
  Bonferroni denominator are NOT the dominant failure axes."
- "Forward motion requires a fresh D-002J pre-registration."

Not permitted:

- any retroactive flip of the D-002H REFUSED verdict;
- any cross-substrate claim;
- any "real-data validated" claim.

### 4.2 Exactly 1 SUPPORTED

Permitted claims:

- "Failure axis &lt;name&gt; is empirically dominant under D-002I
  scope."
- "A fresh D-002J pre-registration designed against axis
  &lt;name&gt; is warranted."

Not permitted:

- "D-002H REFUSED is overturned" — it is not.
- "the canonical sweep should re-run under tuned parameters" —
  any new canonical sweep requires a fresh D-002J/K prereg + a
  fresh 7-gate authorisation chain.

### 4.3 ≥ 2 SUPPORTED

Permitted claims:

- "Multiple confounded failure axes are present."

Not permitted:

- any forward motion without orthogonalising the axes inside a
  fresh D-002J pre-registration.

---

## Section 5 — What claims remain impossible regardless of outcome

D-002I, by construction, can never produce any of the following
claims regardless of outcome path:

- D-002H PASS (the canonical verdict is locked at REFUSED).
- D-002G or D-002C rescue.
- a global systemic-risk conclusion.
- a cross-substrate generalisation (block_structured and
  temporal_coupling remain excluded per D-002G structural closure).
- a canonical-run authorisation under M2 or M6 (out of D-002H scope).

---

## Section 6 — Boundary against substrate redesign

Any substrate code edit is forbidden under D-002I. The substrate
code (`research/systemic_risk/d002c_substrates.py`) stays at its
D-002H-locked sha. Hypothesis H_I3 explicitly parametrises lambda
at the *runner* level — the substrate's lambda accepts the augmented
value as input without any code change.

Any future substrate redesign constitutes a fresh D-002J (or
successor) pre-registration with its own gates, its own canonical
grid, and its own authorisation chain. D-002I is investigation,
not redesign.

---

## Section 7 — Expected runtime per H_I1..H_I4

These are *resource budgets* committed at pre-registration. They
constrain the downstream PRs and prevent runaway compute:

| Hypothesis | Scope                                  | Expected wall-time budget |
|------------|----------------------------------------|---------------------------|
| H_I1       | re-run null audit only x 3 offsets     | ≤ 3 x D-002H null audit time |
| H_I2       | re-run null audit only x 3 tolerances  | ≤ 3 x D-002H null audit time |
| H_I3       | runner-level lambda scaling x 1 grid   | ≤ 1 x D-002H sweep + audit  |
| H_I4       | re-verdict against existing capsule    | seconds (no simulation)      |

D-002H itself ran in ~2294 seconds (`runtime_seconds_total` in the
canonical verdict). H_I1, H_I2, and H_I3 are bounded above by
~3 x that figure each; H_I4 is effectively free.

---

## Section 8 — Decision tree post-investigation

The decision tree is mirrored verbatim from the prereg YAML
`decision_tree` block for the convenience of downstream PR authors:

1. **all 4 REFUTED** → D-002H REFUSED is structural at the tested
   signal magnitude on ricci_flow under M1 ∪ M3. D-002H stays as
   terminal scoped negative artifact; any forward motion is a fresh
   D-002J pre-reg.
2. **exactly 1 SUPPORTED** → identifies a single dominant failure
   axis. Forward motion is a fresh D-002J pre-registration designed
   against that axis only. D-002H REFUSED still stands as canonical
   verdict; D-002I does NOT retroactively flip it.
3. **≥ 2 SUPPORTED** → multiple confounded failure axes. Forward
   motion is a fresh D-002J pre-reg, but the design must
   orthogonalise the axes before any new canonical run can be
   authorised.

In all three branches, D-002H REFUSED remains the truthful canonical
outcome of the D-002H scope. D-002I never rewrites that verdict.
