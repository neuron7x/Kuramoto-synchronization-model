# Intention Lock Protocol

## Purpose

This protocol defines the mandatory pre-action gate for every repository agent operating on GeoSync closure work.

No agent may patch, merge, deploy, rebase, label, close, or score a task before explicitly locking its intention.

The purpose is to prevent impulsive execution, local-contract closure, fake-green optimism, semantic drift, and accidental expansion of intervention scope.

## Core axiom

Action without intention is uncontrolled mutation.

A task is not ready for execution until the agent can name:

1. why the action exists;
2. what state must exist after it;
3. what files, systems, and claims it is allowed to touch;
4. what risk it introduces;
5. what observable condition stops the action.

## Mandatory pre-action record

Before every action, create or state this record:

```yaml
intention_lock:
  action_id:
  target_pr:
  target_issue:
  target_files:
  purpose:
  expected_state:
  intervention_boundary:
  forbidden_scope:
  primary_risk:
  secondary_risks:
  evidence_required:
  stop_criterion:
  rollback_condition:
  owner_role:
  merge_impact:
  ledger_impact:
  cognitive_risk:
  decision:
```

## Field definitions

### action_id

Unique identifier for the action.

Criterion of inclusion:
- one intended state transition;
- one root cause;
- one owner role.

Criterion of exclusion:
- vague batch work;
- broad cleanup;
- mixed unrelated fixes.

### purpose

The reason the action exists.

Valid purpose examples:
- restore real CI measurement;
- close dead invariant;
- bind governance artifact to runtime;
- remove false physics claim;
- synchronize ledger with merged reality.

Invalid purpose examples:
- make CI green;
- clean things up;
- improve docs;
- finish task;
- satisfy previous prompt.

### expected_state

The exact repository state that must exist after the action.

It must be observable.

It must not depend on confidence, memory, or narrative.

### intervention_boundary

The maximum allowed surface of change.

Examples:
- only CI collection logic;
- only neuro validation path and tests;
- only audit ledger JSON and markdown;
- only operation documentation.

If the action needs to cross the boundary, stop and re-intention.

### forbidden_scope

Explicitly named areas the agent must not touch.

This prevents local optimization from mutating adjacent lanes.

### primary_risk

The main way this action can make the system less truthful.

Examples:
- hiding test backlog;
- weakening a gate;
- promoting a metaphor into a physics claim;
- merging on stale SHA;
- creating ledger drift.

### evidence_required

Minimum proof needed before claiming success.

Valid evidence types:
- same-SHA CI;
- local test output;
- commit acceptor;
- exact diff;
- PR check result;
- ledger test;
- runtime witness;
- falsifier test.

### stop_criterion

The precise condition where the action must stop.

Stop criteria must be binary or explicitly tri-state:
- PASS;
- FAIL;
- UNKNOWN.

UNKNOWN cannot promote to PASS.

### rollback_condition

The condition requiring reversal or isolation.

Examples:
- CI failure expands outside declared boundary;
- patch weakens a test;
- metric becomes unknowable;
- semantic drift is detected;
- dependent lane collision appears.

### cognitive_risk

The agent must classify its own risk of misinterpretation.

Allowed values:
- LOW;
- MEDIUM;
- HIGH.

HIGH blocks execution.

MEDIUM permits only bounded read-only recon or minimal patch with explicit verification.

LOW permits execution if all other fields are complete.

## Decision rule

The agent may execute only when:

```yaml
purpose_is_specific: true
expected_state_is_observable: true
boundary_is_explicit: true
forbidden_scope_is_named: true
risk_is_named: true
evidence_required_is_executable: true
stop_criterion_is_binary_or_tristate: true
cognitive_risk: LOW_or_bounded_MEDIUM
```

If any field is missing, the action is blocked.

## Repository-specific intention templates

### #1153 real test oracle

```yaml
intention_lock:
  action_id: restore-real-fast-oracle
  target_pr: 1153
  purpose: prevent CI from passing fast shards with zero selected tests
  expected_state: fast shard collects non-zero test nodeids or fails closed
  intervention_boundary: CI collection logic and first measured import-shadowing root
  forbidden_scope: physics model code, neuro validation code, Q7 worktree
  primary_risk: exposing large hidden backlog and misclassifying it as new regression
  evidence_required: collected test count, same-SHA CI, first-failure classification
  stop_criterion: non-zero collection with green CI or measured quarantine ledger
  rollback_condition: CI rule hides failures or uses permissive bypass
  owner_role: Measurement Owner
  merge_impact: blocks dependent PR merge until terminal or quarantined
  ledger_impact: records measurement-oracle state
  cognitive_risk: MEDIUM
  decision: bounded execution only
```

### #1155 governance runtime binding

```yaml
intention_lock:
  action_id: bind-governance-to-runtime
  target_pr: 1155
  purpose: prevent policy artifact from existing without executable runtime effect
  expected_state: governance kernel is loaded, scored, thresholded, and tested
  intervention_boundary: governance runtime binding and tests
  forbidden_scope: trading claims, physics model behavior, UI routes
  primary_risk: policy theater presented as enforcement
  evidence_required: runtime binding tests, score threshold tests, same-SHA CI
  stop_criterion: governance artifact changes runtime decision path or fails honestly
  rollback_condition: artifact remains documentation-only
  owner_role: Governance Runtime Owner
  merge_impact: requires real test oracle first
  ledger_impact: updates governance binding state
  cognitive_risk: MEDIUM
  decision: wait for #1153 terminal, then revalidate
```

### #1154 neuro invariant

```yaml
intention_lock:
  action_id: close-dopamine-serotonin-dead-invariant
  target_pr: 1154
  purpose: convert declared correlation field into executable trajectory witness
  expected_state: validate_trajectory observes dopamine-serotonin correlation and reports violation, warning, or unknown
  intervention_boundary: neuro integrity validation, tests, related ledger entry
  forbidden_scope: biological overclaim, unrelated neuro model refactor, Q7 worktree
  primary_risk: treating an engineering invariant as biological proof
  evidence_required: fail-before/pass-after tests, flat-channel UNKNOWN test, same-SHA CI
  stop_criterion: C-NEURO-003 resolved with executable witness
  rollback_condition: invariant remains declared but unwitnessed
  owner_role: Neuro Invariant Owner
  merge_impact: blocked until real oracle exists
  ledger_impact: C-NEURO-003 becomes RESOLVED only after witness
  cognitive_risk: MEDIUM
  decision: rebase after #1153, then validate
```

### #1150 Kuramoto scale boundary

```yaml
intention_lock:
  action_id: close-kuramoto-scale-ambiguity
  target_pr: 1150
  purpose: prevent silent K double-scaling or undeclared scale ownership
  expected_state: ambiguous K path fails closed and declared topology path remains valid
  intervention_boundary: Kuramoto configuration boundary and tests
  forbidden_scope: broad Kuramoto refactor, alpha claims, trading performance claims
  primary_risk: compatibility break hidden behind physics correction
  evidence_required: ambiguity rejection test, valid topology acceptance test, same-SHA CI
  stop_criterion: one equation has one scale owner
  rollback_condition: K can enter the system twice or silently
  owner_role: Physics Boundary Owner
  merge_impact: requires real oracle
  ledger_impact: marks K-scaling ambiguity closed only after tests
  cognitive_risk: LOW
  decision: execute after #1153 terminal
```

### #1152 Ricci false-bound correction

```yaml
intention_lock:
  action_id: remove-false-ricci-bound
  target_pr: 1152
  purpose: prevent policy threshold from being described as mathematical kappa bound
  expected_state: margin escalation onset is named as policy threshold, not curvature lower bound
  intervention_boundary: Ricci descriptor semantics, tests, docs
  forbidden_scope: numeric behavior change unless separately justified
  primary_risk: reintroducing false mathematical claim through documentation
  evidence_required: regression tests for kappa values below threshold, same-SHA CI
  stop_criterion: false bound cannot reappear without test failure
  rollback_condition: docs or code imply non-existent kappa lower bound
  owner_role: Physics Boundary Owner
  merge_impact: requires real oracle
  ledger_impact: marks false-bound defect bounded or resolved
  cognitive_risk: LOW
  decision: execute after #1153 terminal
```

### #1147 Q7 route interception

```yaml
intention_lock:
  action_id: close-q7-ecc-runtime-boundary
  target_pr: 1147
  purpose: close ECC coverage with explicit runtime evidence and local-gap boundary
  expected_state: ECC target is proven by CI Playwright or local gap is explicitly bounded
  intervention_boundary: apps/web route-interception specs and PR evidence
  forbidden_scope: backend physics, governance runtime, neuro validation
  primary_risk: claiming local validation when only CI runtime is available
  evidence_required: CI Playwright output, ECC result, same-SHA check status
  stop_criterion: ECC evidence exists or claim is downgraded to bounded
  rollback_condition: ECC claim lacks runtime witness
  owner_role: UI/E2E Owner
  merge_impact: after real oracle and lane-specific evidence
  ledger_impact: Q7 state can close only with runtime witness
  cognitive_risk: MEDIUM
  decision: do not touch external worktree; coordinate only
```

## Enforcement

Any agent output that lacks an intention lock is incomplete.

Any patch without an intention lock is uncontrolled mutation.

Any merge without an intention lock is invalid closure.

Any intention lock with an unobservable expected state is decorative planning.

## Final rule

The intention lock does not prove success.

It only proves the action is allowed to begin.

Verification still decides whether the action was true.
