# Behavioral Program Against Fake Determinism

Status: operational behavior contract for Code Claude and repository agents.

Scope: active GeoSync closure work. This document adds behavioral control rules for situations where deterministic decomposition becomes misleading because local tasks pass while the global repository state drifts.

Read after:

- `docs/operations/first_principles_closure_standard_20260617.md`
- `docs/operations/cognitive_definition_contract_20260617.md`
- `docs/operations/active_geosync_closure_protocol_20260617.md`

Read before:

- patching source code;
- merging a PR;
- declaring a lane closed;
- writing a final verdict.

---

## 1. Core Critique

Modern engineering decomposition can create an illusion of deterministic control.

The repository is split into linear tickets, local acceptance criteria, role-owned lanes, and apparently precise checklists. That structure is useful only if every local closure is continuously coupled back to global runtime truth.

Without that coupling, decomposition becomes dangerous.

A local task may pass while the system becomes less truthful.

A PR may satisfy its local contract while increasing semantic drift.

A green CI status may prove nothing if the test oracle is vacuous.

A governance artifact may look rigorous while no runtime path executes it.

Therefore, a task is not valid because it is decomposed.

A task is valid only if it preserves the system-level invariant it claims to protect.

---

## 2. Corrected Principle

Do not decompose work into lists of steps.

Decompose work into closed verification loops.

Each task must include:

- intent;
- ontology boundary;
- runtime witness;
- falsifier;
- ledger effect;
- rollback condition;
- global drift check.

If any of these is missing, the task is not operationally closed.

It is only described.

---

## 3. Failure Modes

### 3.1 Context Loss

Symptom:

A PR satisfies its own file-level or test-level contract but ignores global repository state.

Examples:

- a ledger PR marks an entry resolved while a later PR supersedes the proof;
- a physics PR changes semantics without updating the scorecard;
- a governance file exists but is not loaded by runtime code;
- an old green CI status is trusted after the test oracle changes.

Agent behavior:

- stop local closure;
- fetch live PR and CI state;
- compare the PR claim against the current canonical ledger;
- update the lane status to PARTIAL if global state is not synchronized.

Operational rule:

Local pass does not imply global closure.

---

### 3.2 Policy Theater

Symptom:

The repository contains a rule, schema, scorecard, threshold, or governance document that is not executed by runtime code or tests.

Examples:

- JSON declares scoring logic but no code reads it;
- a metric exists but no test fails when it is violated;
- a markdown invariant exists but no Python path enforces it;
- a role owns a duty but no checkpoint blocks violation.

Agent behavior:

- classify as POLICY_THEATER;
- require runtime-binding test;
- require fail-before/pass-after witness;
- block PASS until the declared rule has executable consequence.

Operational rule:

If it does not execute, it does not govern.

---

### 3.3 Fake Green

Symptom:

A test, CI job, shard, metric, or scorecard reports success without exercising the intended behavior.

Examples:

- collected tests equal zero;
- shard selection silently filters out all nodeids;
- CI is green on a stale SHA;
- only local tests pass while canonical CI is red;
- warnings replace required failures without being recorded in scorecard.

Agent behavior:

- classify as FAKE_GREEN_RISK;
- block merge;
- restore measurement first;
- rerun dependent PRs under the repaired oracle.

Operational rule:

A green signal without exercised behavior is not evidence.

---

### 3.4 Emergent Semantic Drift

Symptom:

Individually valid changes accumulate into a system that no longer matches its declared ontology.

Examples:

- Ricci descriptor becomes an action-policy claim;
- Kuramoto structure metric becomes implied alpha;
- neuro-inspired heuristic becomes biological assertion;
- closure protocol becomes score inflation;
- exception handling weakens fail-closed physics contracts.

Agent behavior:

- run ontology classification;
- compare claim language to executable witness;
- downgrade claim if witness is heuristic only;
- update ledger and scorecard before final PASS.

Operational rule:

Every claim must keep its ontology label after integration.

---

## 4. Behavioral Programs For Code Claude

### Program A: Pre-Action Intention Lock

Before every patch, output internally:

- What state am I changing?
- Which global invariant does this protect?
- What is the smallest intervention?
- What could become less true after this patch?
- What evidence would prove I am wrong?

If any answer is unknown, do not patch.

---

### Program B: Global Drift Scan

Before declaring any task closed, check:

- active PR list;
- merged PR list;
- current head SHA;
- canonical ledger;
- scorecard;
- dependent lanes;
- CI status under current oracle.

If local state and global state disagree, mark the lane PARTIAL.

---

### Program C: Runtime Witness Requirement

For every claim, identify the witness type:

- TEST_WITNESS;
- CI_WITNESS;
- RUNTIME_BINDING_WITNESS;
- LEDGER_WITNESS;
- PROVENANCE_WITNESS;
- NEGATIVE_FALSIFIER.

If a claim has no witness, classify it as UNSUPPORTED.

If it has a witness but the witness is not executed, classify it as POLICY_THEATER.

---

### Program D: Fake-Green Interruption

If any gate reports PASS while exercising zero behavior:

- stop merging;
- label the lane FAKE_GREEN_RISK;
- fix measurement before fixing downstream behavior;
- revalidate dependent PRs after the oracle changes.

The test oracle has priority over all domain PRs.

---

### Program E: Ontology Boundary Preservation

For every neuro, physics, governance, and trading claim, assign exactly one label:

- IMPLEMENTED_INVARIANT;
- TESTED_HEURISTIC;
- BOUNDED_METAPHOR;
- EMPIRICAL_CLAIM_WITH_GATE;
- UNSUPPORTED_AND_BLOCKED;
- REMOVED.

If the claim cannot be classified, block closure.

If the classification changes after integration, update ledger and scorecard.

---

### Program F: Weakest-Link Verdict

The lane verdict cannot exceed the weakest required metric.

Rules:

- any FAIL blocks PASS;
- any UNKNOWN caps verdict at PARTIAL;
- any stale SHA blocks merge;
- any stale ledger blocks closure;
- any high cognitive risk blocks patching;
- any fake-green risk blocks dependent merges.

No manual override can convert UNKNOWN into PASS.

---

### Program G: Closure Is A State Transition

A task is closed only when all are true:

- patch exists;
- relevant tests pass;
- CI is same-SHA terminal;
- metric source of truth is updated;
- ledger reflects the state;
- scorecard cannot contradict it;
- rollback path exists;
- claim boundary is explicit.

If one item is missing, the task is not closed.

It is only locally improved.

---

## 5. Required Output After Each Agent Action

Use this structure:

```yaml
agent_cognitive_state:
  perception:
  attention:
  memory:
  reasoning:
  decision:
  interpretation_risk:
  cognitive_risk:

task_state:
  active_pr:
  intent:
  expected_state:
  boundary:
  global_invariant:
  local_contract:
  global_drift_check:

verification:
  witness_type:
  commands_or_ci:
  collected_tests:
  same_sha:
  ledger_state:
  scorecard_state:

verdict:
  fake_green_risk:
  policy_theater_risk:
  semantic_drift_risk:
  weakest_required_metric:
  merge_allowed:
  closure_allowed:
  next_action:
```

---

## 6. Integration With Active GeoSync Closure

Apply this document to the active closure stack:

- #1153 must terminalize before dependent PRs can be trusted.
- #1155 must prove governance runtime-binding, not only governance documentation.
- #1154 must close dead invariant through trajectory witness.
- #1150 must preserve single-owner Kuramoto K scaling.
- #1152 must prevent false Ricci mathematical bounds.
- #1147 must bound local Node/Playwright gaps with CI-runtime evidence.
- #1157 must remain draft until the measurement oracle and active closure lanes are terminal or explicitly quarantined.

---

## 7. Final Behavioral Rule

Do not behave like a ticket executor.

Behave like a control system.

A ticket executor asks: did I finish my assigned step?

A control system asks: did this action make the total repository state more truthful, more measurable, and harder to fake?

Only the second behavior is acceptable for this closure protocol.
