# FIRST-PRINCIPLES CLOSURE STANDARD

Status: `DRAFT / NORMATIVE / READ-FIRST / CODE-CLAUDE-EXECUTION-STANDARD`.

Scope: active GeoSync closure work across measurement, governance, neuro-invariant, physics-boundary, UI/E2E, ledger, and final scorecard lanes.

Purpose: define the intellectual and functional values that make repository closure real, measurable, falsifiable, and maintainable.

This document is the top normative layer for the active closure packet. It must be read before:

- `docs/operations/active_geosync_closure_protocol_20260617.md`
- `docs/operations/cognitive_definition_contract_20260617.md`
- `docs/operations/active_geosync_closure_visualization_20260617.md`

---

## 0. Standard Intent

The goal is not to make the repository look complete.

The goal is to make the repository resistant to false completion.

A closure standard is valid only if it prevents these failure modes:

- fake green CI;
- stale canonical state;
- dead invariants;
- unexecuted governance artifacts;
- physics claims without invariant or equivalence tests;
- local-only validation presented as CI truth;
- unresolved backlog hidden by merge pressure;
- agent memory overriding current repository state;
- prose verdict replacing computed verdict.

---

## 1. Reference Discipline

This standard is aligned with established engineering and research-quality principles:

- ACM artifact review: artifact value depends on documentation, consistency, completeness, exercisability, and independent validation.
- NIST SSDF SP 800-218: secure software development should reduce vulnerabilities, mitigate impact, and address root causes.
- SLSA: artifact integrity requires provenance, build integrity, and verification of produced artifacts.
- OpenSSF Scorecard: repository health must be measurable through automated security and maintenance checks.
- Scientific falsifiability: a claim is useful only if it can fail under a defined test.
- Systems engineering: every control must have boundary, owner, feedback signal, and stop criterion.

These references do not prove this repository is correct.

They define the quality bar the repository must satisfy through its own evidence.

---

## 2. Intellectual Values

### V1 — Truth Over Completion

Closure is not a social state.

Closure is a verified state transition.

A PR is not done because it is old, annoying, green-looking, or emotionally expensive.

A PR is done only when evidence survives the required gates.

Operational requirement:

```text
No terminal verdict without same-SHA, non-vacuous, source-of-truth evidence.
```

### V2 — Measurement Before Optimization

No system can be improved faster than it can be measured truthfully.

If the CI oracle can pass `0/0`, then every downstream claim is suspect.

Operational requirement:

```text
#1153 class measurement defects outrank all physics/governance merges.
```

### V3 — Falsifiability Before Confidence

Confidence without a failing condition is theater.

Every claim must define what would falsify it.

Operational requirement:

```text
Each metric must define PASS, PARTIAL, FAIL, UNKNOWN, and escalation.
```

### V4 — One Claim, One Owner, One Witness

Ambiguity multiplies bugs.

Each invariant, metric, or closure claim must have exactly one owning role and at least one executable witness.

Operational requirement:

```text
Declared invariant without validation path = dead invariant.
```

### V5 — Runtime Beats Documentation

Documentation describes intent.

Runtime decides truth.

Governance artifacts that are not loaded, scored, thresholded, or tested are not governance.

Operational requirement:

```text
Policy artifact without runtime binding = policy theater.
```

### V6 — Weakest-Link Integrity

A system cannot be more verified than its weakest required gate.

Operational requirement:

```text
Final verdict = min(required metric states).
PASS is forbidden if any required metric is PARTIAL, FAIL, UNKNOWN, or STALE.
```

### V7 — Bounded Claims Are Stronger Than Big Claims

A bounded claim is engineering.

An oversized claim is future debt.

Operational requirement:

```text
Every physics/neuro claim must be classified as IMPLEMENTED_INVARIANT, TESTED_HEURISTIC, BOUNDED_METAPHOR, EMPIRICAL_CLAIM_WITH_GATE, UNSUPPORTED_AND_BLOCKED, or REMOVED.
```

### V8 — Minimal Intervention, Maximum Evidence

The best patch changes the smallest surface that closes the highest-risk uncertainty.

Operational requirement:

```text
Patch scope must be proportional to root cause, not agent ambition.
```

### V9 — Provenance or It Did Not Happen

Evidence must have origin.

A human/agent summary is not evidence.

Operational requirement:

```text
Evidence requires command, artifact, log, commit SHA, PR number, or test path.
```

### V10 — Cognitive Humility Under Automation

Agents fail through perception errors, stale memory, narrowed attention, and premature closure.

Operational requirement:

```text
HIGH cognitive risk blocks patching and merging.
```

---

## 3. Functional Values

### F1 — Non-Vacuous Test Execution

A test gate must prove it actually tested something.

Required signals:

- collected nodeid count;
- selected nodeid count per shard;
- reason for intentionally empty shard, if any;
- fail-closed behavior when parser output shape changes.

Reject:

- `0/0 pass`;
- hidden `|| true`;
- grep-dependent collection without fallback;
- test count absent from logs.

### F2 — Same-SHA Evidence

The validated commit must be the commit being merged.

Required signals:

- PR head SHA;
- CI checked SHA;
- status rollup;
- required check list.

Reject:

- stale green;
- local-only green;
- pending critical checks;
- manually inferred success.

### F3 — Executable Governance

Governance must run.

Required signals:

- artifact loaded;
- schema validated;
- score computed;
- threshold applied;
- weakest-link clamp tested;
- negative case fails.

Reject:

- JSON file as decoration;
- markdown-only policy;
- scorecard without tests.

### F4 — Physics Boundary Discipline

Physics terms must not exceed their implementation.

Required signals:

- exact equation or algorithm boundary;
- invariant/equivalence test;
- numerical behavior contract;
- explicit no-claim zone.

Reject:

- false mathematical bounds;
- silent scale ownership;
- descriptor promoted to physical model;
- policy threshold named as theorem.

### F5 — Neurosemantic Discipline

Neuro terms must be engineering contracts, not biological theater.

Required signals:

- normalized control meaning;
- input/output semantics;
- invariant or heuristic witness;
- explicit biological-claim boundary.

Reject:

- scalar clamp presented as biological proof;
- metaphor presented as mechanism;
- dead config field presented as validation.

### F6 — Ledger as State Machine

The ledger is not a diary.

It is the canonical state machine for closure truth.

Required signals:

- issue id;
- status;
- severity;
- owner lane;
- resolution state;
- resolution ref;
- evidence link;
- last validated commit.

Reject:

- RESOLVED without ref;
- merged PR still IN_PROGRESS;
- markdown/JSON drift;
- PASS scorecard with stale ledger.

### F7 — Explicit Quarantine, Never Hidden Debt

Backlog may be quarantined only if it is made visible and bounded.

Required signals:

- test nodeid;
- failure cluster;
- issue ref;
- owner lane;
- expiry condition;
- count trend.

Reject:

- silent skips;
- widening quarantine without review;
- quarantine used to fake readiness.

---

## 4. Definition of an Elite Closure Standard

An elite closure standard is a system that makes false completion harder than real completion.

It has five layers:

1. Principle layer — why the system refuses fake closure.
2. Metric layer — how the system measures truth.
3. Execution layer — who does what, in what order.
4. Cognitive layer — how the agent detects its own interpretation risk.
5. Evidence layer — what proof survives review.

A repository closure process is elite only if a skeptical reviewer can reproduce the verdict without trusting the author.

---

## 5. Inclusion Criteria

A task belongs inside this closure standard if it affects at least one of:

- CI truth;
- governance runtime binding;
- physics correctness boundary;
- neuro-invariant correctness;
- UI/E2E runtime proof;
- ledger truth;
- final scorecard computation;
- supply-chain/security confidence;
- cognitive interpretation risk.

---

## 6. Exclusion Criteria

A task does not belong inside this closure standard if it is only:

- cosmetic wording;
- broad refactor without closure effect;
- style cleanup unrelated to active gates;
- new feature work;
- speculative architecture;
- performance tuning without regression witness;
- philosophical expansion without executable consequence.

---

## 7. First-Principles Requirements

### R1 — Every Merge Must Reduce a Named Uncertainty

Before merge, declare:

```yaml
uncertainty_reduced:
source_of_uncertainty:
evidence_that_reduced_it:
residual_uncertainty:
```

Merge is forbidden if uncertainty is not reduced.

### R2 — Every Claim Must Have a Failure Surface

Before accepting a claim, declare:

```yaml
claim:
what_would_falsify_it:
test_or_artifact_that_can_falsify_it:
current_result:
```

Claim is forbidden if it cannot fail.

### R3 — Every Metric Must Have a Source of Truth

Before scoring a metric, declare:

```yaml
metric:
source_of_truth:
collection_method:
acceptable_error:
escalation_if_unknown:
```

Metric is forbidden if scored from prose.

### R4 — Every Owner Must Have Authority and Boundary

Before assigning a role, declare:

```yaml
owner:
authority:
boundary:
forbidden_actions:
escalation_path:
```

Ownership is forbidden if authority is symbolic.

### R5 — Every Closure Must Update Canonical State

Before closing a lane, update:

```yaml
ledger_status:
resolution_ref:
scorecard_metric:
last_validated_sha:
```

Closure is forbidden if canonical state remains stale.

### R6 — Every Quarantine Must Be Expiring Debt

Before quarantining failure, declare:

```yaml
test_or_gate:
reason:
issue_ref:
owner:
expiry_condition:
review_trigger:
```

Quarantine is forbidden if it has no expiry condition.

### R7 — Every Agent Action Must Pass Cognitive Risk Gate

Before patching, declare:

```yaml
perception_risk:
attention_risk:
memory_risk:
reasoning_risk:
decision_risk:
interpretation_risk:
overall_cognitive_risk:
```

Patch is forbidden if `overall_cognitive_risk = HIGH`.

### R8 — Every Physics/Neuro Claim Must State Its Ontology

Before merging physics/neuro work, classify:

```yaml
claim:
ontology: IMPLEMENTED_INVARIANT | TESTED_HEURISTIC | BOUNDED_METAPHOR | EMPIRICAL_CLAIM_WITH_GATE | UNSUPPORTED_AND_BLOCKED | REMOVED
runtime_boundary:
evidence:
non_claims:
```

Merge is forbidden if ontology is missing.

### R9 — Every Evidence Artifact Must Be Reproducible

Before final verdict, provide:

```yaml
command:
working_directory:
commit_sha:
input_files:
output_files:
expected_result:
```

Evidence is forbidden if a reviewer cannot rerun or inspect it.

### R10 — Every Final PASS Must Be Computed

Final PASS must be produced by scorecard logic.

Required:

```yaml
required_metrics:
metric_states:
weakest_link_state:
final_verdict:
```

Manual PASS is forbidden.

---

## 8. Elite Reviewer Checklist

A top-tier reviewer should be able to answer YES to all:

- Can I see what uncertainty this PR reduces?
- Can I see what would falsify the claim?
- Can I see the source of truth for every metric?
- Can I see the exact SHA that passed CI?
- Can I see that tests were non-vacuous?
- Can I see owner, boundary, and forbidden actions?
- Can I see whether the PR changes runtime, governance, docs, or only coordination?
- Can I see whether a physics/neuro term is invariant, heuristic, metaphor, empirical claim, unsupported, or removed?
- Can I reproduce or inspect every evidence artifact?
- Can I see why merge is allowed or forbidden?
- Can I see residual risk after the patch?
- Can I see ledger state synchronized with merged reality?

If any answer is NO, the closure standard failed.

---

## 9. Code Claude Mandatory Pre-Action Block

Before each patch or merge decision, Code Claude must output:

```yaml
pre_action_intent:
  active_pr:
  role:
  uncertainty_to_reduce:
  expected_state:
  boundary:
  forbidden_actions:
  required_evidence:
  falsifier:
  cognitive_risk:
  stop_condition:
  merge_allowed_now:
```

No patch may begin before this block exists.

---

## 10. Code Claude Mandatory Post-Action Block

After each patch or merge decision, Code Claude must output:

```yaml
post_action_result:
  active_pr:
  files_changed:
  commands_run:
  evidence_artifacts:
  metrics_changed:
  uncertainty_reduced:
  residual_uncertainty:
  ledger_update_required:
  scorecard_update_required:
  same_sha_ci_state:
  non_vacuous_test_state:
  merge_allowed:
  next_action:
  verdict:
```

No terminal claim may be made before this block exists.

---

## 11. Mastery Bar

This closure packet should demonstrate mastery through behavior, not adjectives.

Visible mastery means:

- it detects fake green before merge;
- it separates measurement defects from product defects;
- it refuses policy theater;
- it binds governance to runtime;
- it separates physics from metaphor;
- it turns dead invariants into executable witnesses;
- it prefers small patches with strong evidence;
- it makes uncertainty explicit;
- it computes final verdict from gates;
- it leaves a future maintainer with less ambiguity, not more documentation weight.

If a reviewer cannot distinguish this from ordinary checklist management, it is not elite.

If a reviewer can see that the system prevents its author from lying to himself, it is elite.

---

## 12. Read Order

Read and apply documents in this order:

1. `first_principles_closure_standard_20260617.md`
2. `active_geosync_closure_protocol_20260617.md`
3. `cognitive_definition_contract_20260617.md`
4. `active_geosync_closure_visualization_20260617.md`

The first document defines why closure must be strict.

The second defines how closure is executed.

The third defines how interpretation failures are blocked.

The fourth makes dependency and readiness structure visible.
