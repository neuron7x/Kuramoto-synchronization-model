# COGNITIVE EVALUATION AND DEFINITION CONTRACT

Status: `DRAFT / OPERATIONAL / CODE-CLAUDE-EXECUTION-PACKET / COGNITIVE-GATE / DEFINITION-CONTRACT`.

Purpose: add a cognitive-state assessment layer and a precise definition layer to the active GeoSync closure protocol.

This file is a coordination artifact. It changes no runtime code, physics model, neuro validation, UI behavior, trading logic, or scientific claim.

---

## 0. Why this contract exists

An agent can execute the right command for the wrong reason.

An agent can merge green CI that measured nothing.

An agent can remember a PR as merged while GitHub still shows it open.

An agent can treat a bounded metaphor as a defect, or an unsupported suspicion as a verified contradiction.

This contract prevents those errors by forcing the agent to evaluate perception, attention, memory, reasoning, decision quality, and interpretation before every repository state transition.

---

## 1. Cognitive Evaluation Gate

Before every action, classify the agent's cognitive state.

Use this structure:

```yaml
cognitive_state:
  perception:
    observed:
    source_of_truth:
    uncertainty:
  attention:
    selected_focus:
    ignored_surface:
    collision_risk:
  memory:
    prior_claims_used:
    live_state_override:
    stale_memory_risk:
  reasoning:
    inference_chain:
    falsifier:
    weakest_assumption:
  decision:
    selected_action:
    rejected_actions:
    stop_condition:
  interpretation_errors:
    possible_errors:
    mitigation:
  verdict:
    cognitive_risk: LOW|MEDIUM|HIGH
```

If cognitive_risk is HIGH, do not patch or merge.

High risk means:

- live-state not fetched;
- CI status inferred from memory;
- PR dependency not checked;
- same-SHA not verified;
- changed files not inspected;
- stale ledger not checked;
- task boundary unclear;
- unsupported suspicion treated as verified fact.

---

## 2. Perception Evaluation

Definition:

Perception is what the agent claims to observe from the repository.

Boundary:

Only live commands, GitHub metadata, diffs, files, tests, logs, and CI checks count as perception.

Inclusion:

- `gh pr view` output;
- `gh pr checks` output;
- GitHub Actions logs;
- exact head SHA;
- actual changed files;
- test output;
- file content.

Exclusion:

- memory;
- previous chat summary;
- PR title alone;
- agent belief;
- expected CI status;
- user intent without evidence.

Operational sense:

A perception claim is usable only if it has a current source path or command output.

Gate:

```text
perception_valid = live_source_present AND source_timestamp_or_sha_current
```

Fail if:

- PR state is described without fetching PR state;
- CI is called green without exact head SHA;
- a file is assumed to exist without reading tree/diff.

---

## 3. Attention Evaluation

Definition:

Attention is the selected surface the agent chooses to work on now.

Boundary:

Attention must stay inside one PR, one blocker class, and one root cause.

Inclusion:

- current blocking PR;
- failing gate;
- exact root cause;
- dependency blocker;
- stale ledger entry;
- active worktree collision.

Exclusion:

- unrelated cleanup;
- broad refactor;
- aesthetic rewrite;
- multiple PRs in one action;
- opportunistic fixes outside boundary.

Operational sense:

Attention prevents the agent from turning one blocker into a swamp.

Gate:

```text
attention_valid = one_pr AND one_root_cause AND one_stop_condition
```

Fail if:

- the action touches files unrelated to the intent;
- the agent opens a new PR while the current blocker only needs a stale-state patch;
- the agent expands from CI-oracle fix into physics behavior changes.

---

## 4. Memory Evaluation

Definition:

Memory is prior context used to guide the next action.

Boundary:

Memory may propose hypotheses, but it cannot prove repository state.

Inclusion:

- previous agent logs as hypotheses;
- memory files as candidate context;
- prior PR summaries as lookup hints.

Exclusion:

- memory as merge evidence;
- memory as CI proof;
- memory as issue-closure proof;
- memory overriding current GitHub state.

Operational sense:

Memory is an index, not a witness.

Gate:

```text
memory_valid = every_memory_claim_revalidated_against_T0_before_use
```

Fail if:

- memory says “merged” but GitHub says open;
- memory says “resolved” but ledger says IN_PROGRESS;
- memory says “green” but current CI is pending or stale.

---

## 5. Reasoning Evaluation

Definition:

Reasoning is the causal chain from evidence to selected action.

Boundary:

Reasoning must be falsifiable.

Inclusion:

- root cause chain;
- dependency ordering;
- risk estimate;
- expected failure mode;
- selected minimal patch.

Exclusion:

- vague confidence;
- metaphor as proof;
- “looks correct”;
- “should pass”;
- broad future promise.

Operational sense:

Reasoning is valid only when the agent can state what would disprove it.

Gate:

```text
reasoning_valid = evidence_chain_present AND falsifier_present AND weakest_assumption_named
```

Fail if:

- no falsifier exists;
- action cannot be tested;
- root cause is a symptom;
- expected state is not measurable.

---

## 6. Decision Evaluation

Definition:

Decision is the chosen next repository state transition.

Boundary:

A decision must choose exactly one transition:

```text
OPEN -> VERIFIED
FAILED -> ROOT_CAUSED
ROOT_CAUSED -> PATCHED
MERGEABLE -> MERGED
BLOCKED -> EXPLICIT_OWNER
```

Inclusion:

- wait for terminal CI;
- patch exact root cause;
- create quarantine ledger;
- update stale ledger;
- merge under policy;
- block with owner.

Exclusion:

- “monitoring” without stop condition;
- “continue later” without owner;
- “mostly green”;
- “merge because local passed”;
- “open another PR” to avoid a red gate.

Operational sense:

Decision quality is measured by whether the repository state becomes less false.

Gate:

```text
decision_valid = selected_transition AND stop_condition AND rollback_or_recovery_path
```

Fail if:

- merge_allowed is true while any required metric is UNKNOWN, FAIL, stale, or pending;
- a red gate is bypassed without explicit policy;
- dependent PRs merge before #1153 terminalizes or has explicit quarantine.

---

## 7. Interpretation Error Evaluation

Definition:

Interpretation error is a wrong meaning assigned to a true observation.

Examples:

- CI green interpreted as correctness while the shard ran 0 tests;
- local pass interpreted as CI proof;
- bounded metaphor interpreted as real defect;
- unsupported suspicion interpreted as verified contradiction;
- PR open interpreted as shipped;
- docs-only artifact interpreted as runtime binding;
- warning interpreted as fail-closed behavior.

Operational sense:

The agent must name possible interpretation errors before acting.

Gate:

```text
interpretation_valid = at_least_one_counterinterpretation_checked
```

Fail if:

- no alternative interpretation is checked;
- source of truth is weaker than the claim;
- semantics are broader than evidence.

---

## 8. Definition Contract

Every object used by the agent must be defined before it is acted upon.

Use this form:

```yaml
definition:
  object:
  exact_definition:
  boundary:
  inclusion_criteria:
  exclusion_criteria:
  operational_meaning:
  proof_required:
  stop_condition:
```

If an object cannot be defined in this form, do not patch it.

---

## 9. Required Definitions

### terminal_verified_state

exact_definition:

A PR or task state where all required same-SHA gates are terminal, required metrics are PASS or explicitly bounded, ledger state is current, and merge policy is satisfied.

inclusion_criteria:

- exact PR head SHA known;
- required checks terminal;
- same-SHA green or explicit BLOCKED state;
- no stale ledger entry;
- no unowned blocker;
- rollback path exists.

exclusion_criteria:

- pending CI;
- stale SHA;
- 0-test CI pass;
- local-only validation;
- PR body claim without test/log evidence;
- unresolved branch protection.

operational_meaning:

Only terminal_verified_state may be used to justify merge or ledger resolution.

---

### real_ci_test_oracle

exact_definition:

A CI test gate that collects real test nodeids, executes them, reports counts, and fails when collection or execution is vacuous.

inclusion_criteria:

- total collected tests > 0;
- shard selected count reported;
- zero collection is fatal unless deterministic partition explicitly assigns zero;
- command stable under pytest 8.x output changes.

exclusion_criteria:

- 0/0 pass;
- grep parser silently selecting no nodeids;
- missing count output;
- `|| true` around failure;
- skipped critical suite without explicit quarantine.

operational_meaning:

No physics/governance/UI PR can be trusted as green until this oracle is restored or explicitly quarantined.

---

### dead_invariant

exact_definition:

A declared config, schema, or doc invariant that has no executable validation path or test witness.

inclusion_criteria:

- field name implies threshold, correlation, invariant, limit, or requirement;
- no validation code reads it;
- no test fails if it is violated;
- docs imply it constrains behavior.

exclusion_criteria:

- field is purely descriptive and documented as non-enforcing;
- field has runtime validation;
- field has fail-before/pass-after test witness.

operational_meaning:

A dead invariant must be either wired into validation or removed/downgraded.

---

### bounded_metaphor

exact_definition:

A neuro/physics term used as design inspiration, explicitly prevented from becoming a runtime, empirical, scientific, or trading claim.

inclusion_criteria:

- term is labeled metaphor, heuristic, advisory, or structural descriptor;
- docs block scientific/production/trading overclaim;
- tests or ledger prevent promotion to unsupported claim.

exclusion_criteria:

- term is used to justify behavior without test;
- term implies biological or physical validity without model evidence;
- term drives risk/position/trading decisions without empirical gate.

operational_meaning:

Bounded metaphors do not require repair unless they leak into runtime claims.

---

### stale_truth

exact_definition:

A repository statement that was true at one SHA or PR state but is false under current live-state.

inclusion_criteria:

- merged PR still listed as IN_PROGRESS;
- open PR described as merged;
- old green CI used after new head SHA;
- ledger and markdown disagree;
- PR body contradicts current diff.

exclusion_criteria:

- historical note clearly labeled as historical;
- current state revalidated and updated.

operational_meaning:

Stale truth must be patched before final scorecard or merge justification.

---

### explicit_quarantine

exact_definition:

A controlled temporary exclusion of known failing tests from a restored real test oracle, with owner, issue reference, failure cluster, and expiry condition.

inclusion_criteria:

- nodeid listed;
- issue_ref present;
- owner_lane present;
- failure_cluster present;
- expiry condition present;
- new unquarantined failures still fail CI.

exclusion_criteria:

- broad glob exclusion;
- no issue ref;
- no expiry;
- hiding collection failure;
- using quarantine to mark final PASS.

operational_meaning:

Quarantine converts unknown red into owned debt without restoring fake green.

---

## 10. Cognitive Output Contract

After every action, append this to the normal output:

```yaml
cognitive_evaluation:
  perception:
    valid: true|false
    evidence:
  attention:
    valid: true|false
    selected_scope:
    ignored_scope:
  memory:
    valid: true|false
    revalidated_claims:
  reasoning:
    valid: true|false
    inference_chain:
    falsifier:
  decision:
    valid: true|false
    transition:
    stop_condition:
  interpretation_errors:
    checked:
    remaining_risk:
  cognitive_risk: LOW|MEDIUM|HIGH

definitions_used:
  - object:
    definition_status: COMPLETE|INCOMPLETE
    operational_meaning:
```

If `cognitive_risk: HIGH`, the agent must stop before patching or merging.

---

## 11. Final Rule

Do not optimize for appearing intelligent.

Optimize for reducing interpretation error under live repository constraints.

A mature agent is not the one that writes the longest explanation.

A mature agent is the one that knows when its own perception, attention, memory, reasoning, or definitions are insufficient to act.
