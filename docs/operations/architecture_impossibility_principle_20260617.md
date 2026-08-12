# ARCHITECTURE IMPOSSIBILITY PRINCIPLE

Status: `DRAFT / NORMATIVE / CODE-CLAUDE-BEHAVIORAL-STANDARD`.

Scope: active GeoSync closure work and future repository-quality gates.

Purpose: convert the principle "do not aim merely for successful compilation; aim for an architecture where whole classes of bugs become structurally impossible" into operational agent behavior.

---

## 1. Core Principle

Do not optimize for successful compilation.

Optimize for architectural states where invalid behavior cannot be represented, selected, or silently accepted.

A passing build is a weak signal.

An unrepresentable bug class is a strong design result.

---

## 2. Verification Axiom

Code without verification is only an illusion of work.

A patch is not work merely because files changed.

A patch is not work merely because it compiles.

A patch is not work merely because an agent reports completion.

A patch becomes engineering work only when it has an executable witness that proves the intended behavior, rejects the invalid behavior, and binds the claim to the current repository state.

Operational rule:

- no verification, no closure;
- no witness, no trust;
- no same-SHA evidence, no merge claim;
- no falsifier, no confidence;
- no structural block, no architecture improvement.

If the agent cannot identify the verification path, it must classify the task as `UNVERIFIED_CHANGE`, not `DONE`.

---

## 3. Definition

Architecture impossibility means that a defect class is prevented by structure before it reaches runtime.

A bug is structurally impossible when at least one of these holds:

- the invalid state cannot be constructed;
- the invalid transition is rejected at the boundary;
- the invalid claim cannot enter the ledger without evidence;
- the invalid metric cannot score as PASS;
- the invalid CI state cannot appear green;
- the invalid ontology cannot be merged as a physics/neuro claim;
- the invalid agent action is blocked by cognitive or governance gates.

---

## 4. Inclusion Criteria

Use this principle when a task affects:

- CI truth;
- physics or neuro invariants;
- governance runtime binding;
- scorecard computation;
- ledger state;
- quarantine policy;
- claim ontology;
- agent decision gates;
- merge eligibility.

---

## 5. Exclusion Criteria

Do not invoke this principle for:

- cosmetic refactors;
- wording-only polish;
- style-only edits;
- broad rewrites without a defect class;
- optimization without an invariant;
- documentation that does not alter an executable or reviewable gate.

---

## 6. Operational Translation

For every active PR, the agent must identify which defect class becomes harder or impossible after the patch.

Required field:

```yaml
impossibility_target:
  defect_class:
  current_possible_path:
  structural_block_after_patch:
  executable_witness:
  residual_escape_path:
  owner:
  stop_condition:
```

If `structural_block_after_patch` is empty, the task is not architecture closure.

Verification field:

```yaml
verification_witness:
  intended_behavior:
  invalid_behavior_rejected:
  command_or_ci_gate:
  same_sha_evidence:
  falsifier:
  residual_unverified_area:
```

If `verification_witness` is empty, the task is not complete.

---

## 7. Examples in Active GeoSync Closure

### #1153 — Vacuous Fast-Green CI

Defect class:
  CI shard passes while running zero selected tests.

Current possible path:
  collection parser returns no nodeids, shard passes as 0/0.

Structural block:
  zero selected tests becomes fatal unless explicitly justified.

Executable witness:
  CI log reports non-zero collected and selected test counts.

Result:
  fake green becomes structurally impossible for this shard class.

### #1154 — Dead Neuro Invariant

Defect class:
  config declares dopamine/serotonin correlation invariant but no validation path reads it.

Current possible path:
  field exists, tests pass, invariant never executes.

Structural block:
  trajectory validation reads the field and emits measurable violation/UNKNOWN state.

Executable witness:
  fail-before/pass-after tests around trajectory correlation.

Result:
  declared-but-unwitnessed invariant becomes structurally harder to introduce.

### #1150 — Kuramoto K-Scale Ambiguity

Defect class:
  scale can be silently applied at the wrong ownership boundary.

Current possible path:
  ambiguous adjacency_kind with K != 1 can continue as warning.

Structural block:
  ambiguous scale ownership raises at construction boundary.

Executable witness:
  tests prove invalid K path fails closed.

Result:
  double-scaling ambiguity becomes structurally impossible at that boundary.

### #1152 — False Ricci Bound

Defect class:
  policy threshold is named as a mathematical curvature bound.

Current possible path:
  documentation or code implies false bound.

Structural block:
  naming and tests separate policy onset from curvature theorem.

Executable witness:
  tests preserve numerical behavior while preventing false-bound semantics.

Result:
  false mathematical claim becomes review-detectable and test-guarded.

### #1155 — Governance Theater

Defect class:
  governance artifact exists but runtime never loads, scores, or thresholds it.

Current possible path:
  JSON policy file creates illusion of control.

Structural block:
  runtime binding loads artifact, computes score, applies weakest-link clamp.

Executable witness:
  positive and negative governance tests.

Result:
  non-executed governance becomes harder to pass as real governance.

---

## 8. Agent Behavioral Rule

Before writing any patch, Code Claude must answer:

```yaml
before_patch:
  what_bug_class_becomes_impossible:
  why_compilation_is_insufficient:
  where_the_invalid_state_enters_today:
  which_boundary_will_reject_it_after_patch:
  which_test_or_gate_proves_rejection:
```

If the answer is vague, do not patch.

After writing any patch, Code Claude must answer:

```yaml
after_patch:
  verification_status: VERIFIED | PARTIAL | UNVERIFIED
  evidence_source:
  same_sha_or_local_only:
  invalid_state_rejected:
  regression_guard_added:
  remaining_escape_path:
```

If `verification_status` is `UNVERIFIED`, the task must not be called complete.

---

## 9. Closure Rule

A task is not complete because it compiles.

A task is complete when the repository structure rejects a previously possible invalid state, transition, claim, or verdict.

Compilation is the floor.

Verification is the witness.

Structural impossibility is the target.

---

## 10. Final Review Question

The reviewer must ask:

Did this PR merely make the current code pass, or did it make a class of future failure harder or impossible?

Did this PR merely change files, or did it verify behavior against an executable witness?

Only the second answer in both questions qualifies as elite closure.
