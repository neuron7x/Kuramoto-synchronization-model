# Verification Protocol v2026-06-17

## Status

Normative verification layer for PR #1157.

This protocol defines how Code Claude, reviewers, and repository agents must verify claims, data, conclusions, and actions before declaring closure.

## 0. Purpose

Verification is the act of matching a statement, datum, conclusion, or action against one of four anchors:

1. source record;
2. protocol requirement;
3. executable specification;
4. observable runtime fact.

A claim without an anchor is not evidence.

A patch without a witness is not closure.

A green status without same-SHA execution is not verification.

## 1. Core Axiom

Code without verification is only an illusion of work.

Verification converts code from text into observed behavior.

## 2. Scope

This protocol applies to:

- PR bodies;
- issue closure comments;
- audit ledgers;
- scorecards;
- governance artifacts;
- physics and neuro claims;
- CI/test conclusions;
- deployment statements;
- agent final reports.

## 3. Verification Objects

Every assertion must be classified before use.

### CLAIM

A natural-language statement about behavior, architecture, risk, or status.

Example:

- fast-shard no longer passes vacuously.
- governance kernel is runtime-bound.
- dead invariant is resolved.

### DATA

A measured or stored value.

Example:

- collected test count;
- CI head SHA;
- ECC score;
- ledger status;
- correlation value.

### CONCLUSION

An inference derived from claims and data.

Example:

- merge is allowed;
- PR is blocked;
- verdict is PARTIAL;
- metric is PASS.

### ACTION

A repository state transition.

Example:

- merge PR;
- close issue;
- mark ledger entry RESOLVED;
- promote protocol to enforced state.

## 4. Anchor Types

Every verification object must reference at least one anchor.

### SOURCE_RECORD

Repository source of truth:

- current git tree;
- PR diff;
- issue or PR metadata;
- audit JSON;
- scorecard JSON;
- workflow logs;
- committed documentation.

### PROTOCOL_REQUIREMENT

A rule defined in the closure protocol:

- first-principles standard;
- operationalization protocol;
- Metrics v2;
- cognitive definition contract;
- behavioral anti-fake-green program;
- deployment runtime protocol;
- architecture impossibility principle.

### EXECUTABLE_SPECIFICATION

A machine-checkable witness:

- unit test;
- integration test;
- CI job;
- acceptor;
- schema validator;
- scorecard test;
- runtime binding script.

### OBSERVABLE_FACT

A directly observed execution result:

- same-SHA CI green;
- non-zero test collection;
- test failure log;
- runtime output;
- metric value;
- mergeability state.

## 5. Verification Matrix

Each claim must be written in this shape:

```yaml
verification_record:
  object_type: CLAIM|DATA|CONCLUSION|ACTION
  statement: "..."
  anchor_type: SOURCE_RECORD|PROTOCOL_REQUIREMENT|EXECUTABLE_SPECIFICATION|OBSERVABLE_FACT
  anchor_ref: "file, test, PR, CI job, log, schema, metric, or line reference"
  observed_value: "..."
  expected_value: "..."
  comparison: MATCH|MISMATCH|UNKNOWN
  confidence: HIGH|MEDIUM|LOW
  decision: PASS|PARTIAL|FAIL|BLOCKED
```

## 6. Pass, Partial, Fail, Blocked

### PASS

Allowed only when:

- source exists;
- requirement is explicit;
- executable witness exists;
- observed fact matches expected state;
- same-SHA state is known if CI is involved.

### PARTIAL

Required when:

- local result exists but CI is pending;
- source exists but witness is incomplete;
- claim is bounded but not fully enforced;
- runtime gap is documented;
- metric is UNKNOWN but non-critical.

### FAIL

Required when:

- observed fact contradicts claim;
- test fails;
- CI is red;
- ledger state is stale;
- claim has no evidence;
- result depends on 0/0 test collection.

### BLOCKED

Required when:

- required source is unavailable;
- active dependency is not terminal;
- mergeability cannot be computed;
- owner lane is explicit but unfinished;
- quarantine decision is pending.

## 7. Verification Rules

### Rule 1: No unanchored closure

No issue, PR, or ledger entry may be closed from natural-language confidence alone.

### Rule 2: Same-SHA or no CI claim

A CI claim must include the exact commit SHA it verifies.

### Rule 3: Zero-test execution invalidates green

A test job that collects zero tests cannot be used as evidence of correctness.

### Rule 4: Runtime beats documentation

If documentation says a protocol is enforced but runtime does not execute it, the claim is FAIL or PARTIAL, never PASS.

### Rule 5: Local pass is not global pass

Local validation is useful evidence, but merge permission requires repository-level constraints and same-SHA CI where applicable.

### Rule 6: Ledger resolution requires resolution reference

A RESOLVED ledger entry must reference the PR, commit, test, or scorecard that resolved it.

### Rule 7: Physics claims require behavioral witness

A physics correction must have one of:

- invariant test;
- equivalence test;
- calibration witness;
- explicit bounded-claim demotion.

### Rule 8: Governance claims require runtime binding

Governance is not a document. Governance exists only when a rule constrains execution.

### Rule 9: Verification must include falsifier

A verification record must state what observation would make the claim false.

### Rule 10: Unknown lowers verdict

UNKNOWN cannot produce PASS. It caps the lane verdict at PARTIAL unless explicitly non-critical.

## 8. Falsifier Contract

Every meaningful claim must include:

```yaml
falsifier:
  claim: "..."
  would_be_false_if:
    - "..."
  detection_method: "test, CI job, schema, audit, runtime log, or manual observation"
  response_if_false: "block, patch, revert, quarantine, or downgrade verdict"
```

## 9. Verification Workflow

### Stage 1: Identify object

Classify the object as CLAIM, DATA, CONCLUSION, or ACTION.

### Stage 2: Locate anchor

Find the source record, protocol requirement, executable specification, or observable fact.

### Stage 3: Compare

Compare expected state against observed state.

### Stage 4: Assign verdict

Use PASS, PARTIAL, FAIL, or BLOCKED.

### Stage 5: Record residual risk

Name what remains unproven.

### Stage 6: Select next action

Only act if the next action reduces uncertainty, removes stale truth, or blocks a defect class.

## 10. Verification Examples

### Example A: fast-shard claim

```yaml
verification_record:
  object_type: CLAIM
  statement: "fast-shard executes real tests"
  anchor_type: OBSERVABLE_FACT
  anchor_ref: "GitHub Actions fast-shard log for exact head SHA"
  observed_value: "collected_tests > 0"
  expected_value: "collected_tests > 0 and no 0/0 pass"
  comparison: MATCH
  confidence: HIGH
  decision: PASS
```

### Example B: dead invariant claim

```yaml
verification_record:
  object_type: CONCLUSION
  statement: "C-NEURO-003 is resolved"
  anchor_type: EXECUTABLE_SPECIFICATION
  anchor_ref: "validate_trajectory correlation test + ledger resolution_ref"
  observed_value: "test passes and ledger points to resolving PR"
  expected_value: "runtime witness plus RESOLVED ledger entry"
  comparison: MATCH
  confidence: HIGH
  decision: PASS
```

### Example C: governance claim

```yaml
verification_record:
  object_type: CLAIM
  statement: "governance kernel is deployed"
  anchor_type: EXECUTABLE_SPECIFICATION
  anchor_ref: "runtime binding test or CI enforcement gate"
  observed_value: "kernel is loaded and constrains execution"
  expected_value: "documented rule is executed"
  comparison: MATCH|MISMATCH
  confidence: HIGH|LOW
  decision: PASS|FAIL
```

## 11. Agent Output Requirement

After every task, the agent must output:

```yaml
verification_summary:
  active_pr:
  head_sha:
  verified_objects:
    - object_type:
      statement:
      anchor_ref:
      comparison:
      decision:
  failed_or_unknown:
  residual_risk:
  next_action:
  merge_allowed:
  verdict:
```

## 12. Stop Rules

Stop execution if:

- the claim cannot be anchored;
- CI head SHA is stale;
- the test oracle is vacuous;
- ledger and runtime disagree;
- a required falsifier is missing;
- cognitive risk is HIGH;
- the next action would broaden scope without reducing uncertainty.

## 13. Promotion Rule

The verification protocol is not deployed until at least one active PR uses it to block, patch, downgrade, quarantine, or merge a real lane.

A document that never changes execution is not a protocol.

It is decoration.

## 14. External Method References

- NIST SSDF: secure software development and verification discipline.
- NIST AI RMF: govern, map, measure, manage trustworthy AI-system risk.
- SLSA: provenance and build-integrity requirements.
- OpenSSF Scorecard: measurable repository security posture.
- ACM Artifact Review: documented, consistent, complete, exercisable, validated, and reproducible artifacts.

## 15. Final Principle

Verification is not a final report.

Verification is a constraint on action.

If a claim cannot change what the agent is allowed to do, it is not yet operational verification.
