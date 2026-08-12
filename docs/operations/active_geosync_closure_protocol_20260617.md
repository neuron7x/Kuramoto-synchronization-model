# OPERATIONALIZATION PROTOCOL: ACTIVE GEOSYNC CLOSURE

Status: `DRAFT / OPERATIONAL / CODE-CLAUDE-EXECUTION-PACKET / METRICS-V2 / DO-NOT-MERGE-BEFORE-#1153`.

Purpose: convert the active GeoSync PR surface into terminal verified states through actions, owners, resources, calibrated metrics, checkpoints, and stop criteria.

This is a coordination artifact. It changes no runtime code, physics model, neuro validation, UI behavior, trading logic, or scientific claim.

---

## 0. Mission

Convert the active PR surface into terminal verified states.

No reports as substitutes for action.

Allowed transitions only:

```text
OPEN -> VERIFIED -> MERGEABLE -> MERGED
OPEN -> FAILED -> ROOT_CAUSED -> PATCHED
OPEN -> BLOCKED -> EXPLICIT_OWNER
```

Hard law: a PR is not true because it is green. A PR is true only if the same head SHA passed the correct non-vacuous gates.

---

## 1. Live-State Rule

Before every action, run live-state discovery.

```bash
git fetch origin --prune
gh pr list --repo neuron7xLab/GeoSync --state open --json number,title,headRefName,headRefOid,isDraft,mergeable,mergeStateStatus
```

If live-state differs from this document, live-state wins.

Known active lanes at protocol creation:

- `#1153` — Measurement Owner: restore real CI fast-test oracle.
- `#1155` — Governance Runtime Owner: bind governance kernel to runtime.
- `#1154` / possible successor lane — Neuro Invariant Owner: close dopamine/serotonin correlation invariant.
- `#1150` — Physics Boundary Owner: close Kuramoto K-scaling ambiguity.
- `#1152` — Physics Boundary Owner: remove false Ricci bound / policy-threshold confusion.
- `#1147` — UI/E2E Owner: close Q7 ECC with CI-runtime boundary.
- ledger/scorecard — sync merged PRs into resolved truth state.

---

## 2. Roles

### ROLE_A: Measurement Owner

Owns: `#1153`.

Duty: restore the real CI test oracle.

Success means:

- fast-shard collects non-zero tests;
- zero-test collection is fatal;
- known failures are fixed or quarantined with issue references;
- no dependent PR is merged on fake green.

### ROLE_B: Governance Runtime Owner

Owns: `#1155`.

Duty: ensure declared governance kernel is executable, not policy theater.

Success means:

- JSON kernel is loaded by runtime code;
- score is computed;
- thresholding is applied;
- weakest-link clamping is tested;
- governance artifact is not documentation-only.

### ROLE_C: Neuro Invariant Owner

Owns: `#1154` or its successor PR.

Duty: close the dopamine/serotonin dead invariant with executable trajectory witness.

Success means:

- `validate_trajectory()` computes dopamine/serotonin correlation;
- positive correlation above threshold is surfaced;
- inverse relation passes;
- constant or zero-variance channel returns `NaN` or `UNKNOWN`, not fake health;
- `C-NEURO-003` is updated only after evidence exists.

### ROLE_D: Physics Boundary Owner

Owns: `#1150` and `#1152`.

Duty: close Kuramoto K-scaling and Ricci false-bound defects.

Success means:

- ambiguous K-scaling fails closed;
- valid normalized topology still passes;
- false Ricci lower-bound language cannot return;
- no numeric behavior changes without golden/equivalence proof.

### ROLE_E: UI/E2E Owner

Owns: `#1147`.

Duty: close Q7 ECC with CI-runtime boundary.

Success means:

- ECC >= 0.90 is proven by CI Playwright or equivalent runtime evidence;
- local Node/Playwright gap is explicitly bounded if not locally reproduced;
- no local-validation claim is made without actual local execution.

### ROLE_F: Ledger Owner

Owns: audit ledger and scorecard.

Duty: sync merged PRs into `RESOLVED` states.

Success means:

- every merged PR becomes `RESOLVED` with `resolution_ref`;
- no merged PR remains `IN_PROGRESS`;
- final scorecard is computed by tests, not prose.

---

## 3. Resources

Required resources:

- GitHub CLI;
- GitHub Actions logs;
- `pytest`;
- `ruff`;
- `black`;
- `mypy`;
- commit acceptor validator;
- `scripts/ci/verify_changeset.py` if present;
- PR bodies;
- audit ledger JSON;
- scorecard JSON.

Forbidden resources:

- memory-only claims;
- green status without exact SHA;
- local result used as substitute for CI;
- CI result with zero collected tests;
- stale PR body used as proof;
- agent summary used as proof.

---

## 4. Execution Order

### STEP_1: Terminalize `#1153` first.

Reason: no other green CI can be trusted while fast-shard can pass `0/0`.

### STEP_2: Revalidate `#1155` under real oracle.

Reason: governance runtime-binding must not merge on fake CI.

### STEP_3: Rebase and validate `#1154` or successor neuro invariant PR.

Reason: dead invariant closure depends on real test execution and ledger state.

### STEP_4: Revalidate `#1150` and `#1152`.

Reason: physics PRs require real test oracle before merge.

### STEP_5: Validate `#1147`.

Reason: Q7 must be bounded by CI Playwright if local Node gap remains.

### STEP_6: Ledger sync.

Reason: merged PRs must become `RESOLVED` with `resolution_ref`.

### STEP_7: Final scorecard.

Reason: only after all active lanes are terminal.

---

## 5. Metrics v2: calibrated, falsifiable, weakest-link based

Every metric must have:

```yaml
id:
owner:
source_of_truth:
formula_or_test:
target:
partial:
fail:
escalation:
```

No metric may be scored from prose alone.

Final readiness is the weakest-link value across required metrics.

```text
PASS requires every required metric PASS.
PARTIAL if any required metric is PARTIAL or UNKNOWN.
FAIL if any required metric FAIL.
```

### M1 — CI Oracle Integrity

owner: ROLE_A.

source_of_truth: `gh pr checks`, GitHub Actions logs, collected nodeid count.

formula_or_test:

```text
fast_total_collected = sum(collected nodeids across fast shards)
fast_selected_per_shard[i] > 0 OR shard explicitly has zero assigned nodeids by deterministic partitioning
```

target:

- `fast_total_collected > 0`;
- every shard prints collected and selected counts;
- zero selected because of parser failure is fatal;
- collection command is stable under pytest 8.x verbosity changes.

partial:

- collection fixed, but backlog failures remain classified.

fail:

- any shard passes from `0/0`;
- collected nodeids are not printed;
- parser depends on fragile text shape without fallback.

escalation:

- if more than 3 failure clusters appear after 2 CI cycles, create quarantine ledger instead of blind drain.

### M2 — Same-SHA CI Truth

owner: all roles.

source_of_truth: PR head SHA and statusCheckRollup.

formula_or_test:

```text
checked_sha == pr_head_sha AND all required checks terminal success
```

target:

- same-SHA green;
- no pending, cancelled, skipped critical, stale, or manually assumed checks.

partial:

- local green but CI pending;
- CI green on stale SHA.

fail:

- any required check red;
- PR body claims green without exact SHA.

escalation:

- re-run or push a no-op only if required by stale check policy.

### M3 — Runtime Binding Coverage

owner: ROLE_B.

source_of_truth: runtime tests and governance kernel tests.

formula_or_test:

```text
artifact_loaded == true
score_computed == true
threshold_applied == true
weakest_link_clamp_tested == true
```

target:

- declared governance artifact is executed by code;
- at least one negative test proves threshold failure is observable.

partial:

- artifact loads but no negative test.

fail:

- JSON exists but runtime never reads it;
- score is prose-only.

escalation:

- block merge as policy-theater regression.

### M4 — Invariant Witness Density

owner: ROLE_C and ROLE_D.

source_of_truth: tests, invariant modules, ledger.

formula_or_test:

```text
witness_density = executable_invariant_tests / declared_invariants
```

target:

- every declared invariant has at least one executable witness;
- target `witness_density = 1.0` for touched scope.

partial:

- invariant implemented but no fail-before/pass-after evidence.

fail:

- config declares invariant with no validation path;
- physics claim has no invariant/equivalence test.

escalation:

- either implement witness or delete/downgrade claim.

### M5 — Physics Ambiguity Closure

owner: ROLE_D.

source_of_truth: Kuramoto/Ricci tests and docs-runtime alignment.

formula_or_test:

```text
ambiguous_scale_paths == 0
false_physics_bounds == 0
unbacked_numeric_behavior_changes == 0
```

target:

- K-scale ambiguity fails closed;
- false Ricci bound cannot reappear;
- any numeric behavior change has golden/equivalence evidence.

partial:

- docs corrected but behavior not guarded.

fail:

- warning remains where fail-closed is required;
- mathematical bound is claimed without theorem/test.

escalation:

- keep PR open until invariant tests exist.

### M6 — ECC Runtime Evidence

owner: ROLE_E.

source_of_truth: CI Playwright job, ECC artifact/output, PR body boundary.

formula_or_test:

```text
ECC >= 0.90 AND runtime_evidence_present == true
```

target:

- ECC >= 0.90 with CI runtime proof;
- local Node gap explicitly bounded if local run unavailable.

partial:

- CI runtime proof exists, local reproduction unavailable and bounded.

fail:

- ECC claim without runtime evidence;
- local validation claimed but not executed.

escalation:

- block merge or mark CI-only boundary.

### M7 — Ledger Freshness and Closure Integrity

owner: ROLE_F.

source_of_truth: audit ledger JSON, markdown ledger, merged PR list.

formula_or_test:

```text
stale_entries = count(merged_pr_ref still marked IN_PROGRESS)
invalid_resolutions = count(RESOLVED without resolution_ref)
json_doc_drift = count(JSON status != markdown status)
```

target:

- `stale_entries = 0`;
- `invalid_resolutions = 0`;
- `json_doc_drift = 0`.

partial:

- merged PR exists but ledger sync PR pending.

fail:

- scorecard PASS while ledger stale.

escalation:

- run ledger sync before scorecard.

### M8 — Backlog Quarantine Discipline

owner: ROLE_A plus lane owner.

source_of_truth: quarantine ledger if created.

formula_or_test:

```text
quarantined_tests_all_have_issue_ref == true
new_unquarantined_failures == 0
quarantine_count_delta_requires_review == true
```

target:

- known backlog is visible, owned, expiring, and not hidden by `|| true`.

partial:

- backlog measured but not yet classified.

fail:

- failures silently ignored;
- quarantine entries lack owner or expiry condition.

escalation:

- create issue-cluster PRs, not one giant swamp PR.

### M9 — Evidence Minimality

owner: all roles.

source_of_truth: PR diff, commands, tests.

formula_or_test:

```text
every_changed_file_maps_to_intent == true
every_claim_maps_to_command_or_test == true
```

target:

- minimal diff;
- no scope leak;
- no aesthetic changes without gate impact.

partial:

- harmless extra doc line with no claim expansion.

fail:

- unrelated refactor;
- claim in PR body not proven by diff/test.

escalation:

- split PR or revert scope leak.

### M10 — Merge Readiness Composite

owner: Ledger Owner verifies; lane owner supplies evidence.

source_of_truth: M1-M9.

formula_or_test:

```text
merge_readiness = min(required_metric_statuses)
```

target:

- required metrics all PASS;
- explicit PARTIAL allowed only for bounded non-blocking lanes.

fail:

- any required metric FAIL;
- any metric UNKNOWN for current lane.

escalation:

- do not merge; return exact failing metric.

---

## 6. Checkpoints

### CHECKPOINT_1

`#1153` either green with real tests or has measured failure ledger.

Stop if: backlog shape is unknown.

### CHECKPOINT_2

`#1155` passes after `#1153`.

Stop if: governance runtime test fails.

### CHECKPOINT_3

`#1154` or successor neuro invariant PR passes after rebase.

Stop if: correlation invariant warning/error semantics are unclear.

### CHECKPOINT_4

`#1150` and `#1152` pass after real oracle.

Stop if: physics behavior changes without golden/equivalence evidence.

### CHECKPOINT_5

`#1147` has CI Playwright evidence or explicit bounded local gap.

Stop if: ECC claim lacks runtime proof.

### CHECKPOINT_6

Ledger JSON and markdown agree.

Stop if: `RESOLVED` entry lacks `resolution_ref`.

### CHECKPOINT_7

Scorecard computes `PASS`, `PARTIAL`, or `FAIL`.

Stop if: verdict is hand-written prose.

---

## 7. Task Cards

### TASK_CARD_1153

Intent: restore measurement instrument.

Expected state: fast-shard executes real tests.

Boundary: CI collection logic + first import-shadowing root + optional quarantine ledger.

Risk: backlog expansion.

Stop: non-zero tests collected and CI terminal.

Required action:

```bash
gh pr view 1153 --repo neuron7xLab/GeoSync --json headRefOid,statusCheckRollup,mergeable,isDraft
gh pr checks 1153 --repo neuron7xLab/GeoSync
```

If failing, read failing logs and patch exact root cause.

Known first root to verify: `tests/unit/cli/test_amm_cli.py` import shadowing where CI may resolve `cli` to `scripts/cli.py`.

If backlog expands:

- if <= 3 clusters and <= 20 tests: drain in `#1153`;
- if > 3 clusters or unknown after 2 CI cycles: create quarantine ledger.

Quarantine entry must contain:

```yaml
nodeid:
  failure_cluster:
  issue_ref:
  owner_lane:
  expiry_condition:
```

### TASK_CARD_1155

Intent: bind governance kernel to runtime.

Expected state: JSON scoring pipeline is executable.

Boundary: governance only, no physics/trading claim.

Risk: policy-theater regression.

Stop: runtime binding tests + same-SHA CI green.

Required validation:

```bash
PYTHONPATH=. python -m pytest -q tests/governance
python tools/commit_acceptor/validate_commit_acceptor.py --require-acceptor-for-code-change
git diff --check
```

### TASK_CARD_1154

Intent: close `C-NEURO-003`.

Expected state: dopamine/serotonin correlation invariant checked in trajectory.

Boundary: neuro validation only.

Risk: overclaiming biology from engineering correlation.

Stop: fail-before/pass-after tests green.

Required validation:

```bash
mypy --strict core/validation/neuro_integrity.py
ruff check core/validation tests/unit/validation
black --check core/validation tests/unit/validation
PYTHONPATH=. python -m pytest -q tests/unit/validation/test_neuro_integrity.py
```

Ledger rule: only mark `C-NEURO-003` as `RESOLVED` after executable proof exists.

### TASK_CARD_1150

Intent: close K-scaling ambiguity.

Expected state: ambiguous K path fails closed.

Boundary: Kuramoto config boundary.

Risk: caller compatibility.

Stop: ambiguous K rejected, valid topology accepted.

Required evidence:

- undeclared adjacency with `K != 1` fails closed;
- declared normalized topology remains valid;
- full-weight matrix with extra K is rejected;
- no broad Kuramoto refactor.

### TASK_CARD_1152

Intent: remove false Ricci bound.

Expected state: margin escalation onset named as policy threshold, not mathematical `kappa_F` bound.

Boundary: Ricci margin semantics only.

Risk: docs reintroduce false math.

Stop: tests prevent false bound.

Required evidence:

- tests prove relevant negative kappa cases floor to base margin if expected;
- docs cannot imply false lower-bound theorem;
- numeric behavior unchanged unless explicitly scoped.

### TASK_CARD_1147

Intent: finish Q7 ECC.

Expected state: `ECC >= 0.90` with runtime evidence.

Boundary: apps/web route-interception specs.

Risk: local Node gap.

Stop: CI Playwright green or bounded gap documented.

Required validation:

```bash
gh pr view 1147 --repo neuron7xLab/GeoSync --json headRefOid,statusCheckRollup,mergeable,isDraft
gh pr checks 1147 --repo neuron7xLab/GeoSync
```

If local Node/Playwright is unavailable:

- do not claim local verification;
- bound the claim to GitHub Actions runtime;
- require same-SHA CI proof.

### TASK_CARD_LEDGER

Intent: synchronize truth.

Expected state: every merged PR reflected in ledger.

Boundary: audit JSON/markdown/scorecard only.

Risk: stale canonical state.

Stop: ledger tests green.

Required validation:

```bash
PYTHONPATH=. python -m pytest -q tests/audit/test_contradiction_ledger.py
python -m compileall -q tests/audit/test_contradiction_ledger.py
git diff --check
```

---

## 8. Control Rules

RULE_1: Do not merge dependent PRs before `#1153` terminalizes or has an explicit quarantine ledger.

RULE_2: If `#1153` exposes many failures, create quarantine ledger instead of draining blindly.

RULE_3: If a PR is green only under old vacuous oracle, re-run after `#1153`.

RULE_4: If a PR claims runtime-binding, require runtime execution test.

RULE_5: If a PR claims physics correction, require invariant or equivalence test.

RULE_6: If a PR claims closure, update ledger in the same PR or immediate follow-up PR.

RULE_7: Final scorecard cannot be `PASS` while any active PR is open or stale.

RULE_8: If a PR is blocked by branch protection, report exact blocker and do not bypass silently.

RULE_9: If a metric is UNKNOWN, the lane verdict cannot exceed PARTIAL.

RULE_10: If a metric fails because the measurement instrument is broken, fix the instrument before interpreting the lane.

---

## 9. Output After Each Action

Return exactly this structure:

```yaml
repo_state:
active_pr:
responsible_role:
intent:
expected_state:
boundary:
resources_used:
commands_run:
metrics:
  M1_ci_oracle_integrity:
  M2_same_sha_ci_truth:
  M3_runtime_binding_coverage:
  M4_invariant_witness_density:
  M5_physics_ambiguity_closure:
  M6_ecc_runtime_evidence:
  M7_ledger_freshness:
  M8_backlog_quarantine_discipline:
  M9_evidence_minimality:
  M10_merge_readiness_composite:
checkpoint:
risk:
stop_criterion_met:
merge_allowed:
next_action:
verdict:
```

No motivational text.

No broad summaries.

No future promises without a scheduled action.

---

## 10. Final Gate

The closure program is complete only when:

```yaml
real_test_oracle: PASS
governance_runtime_binding: PASS
dead_invariants: 0
physics_ambiguity: 0
q7_runtime_boundary: PASS_or_BOUNDED
ledger_staleness: 0
backlog_quarantine: PASS_or_NOT_REQUIRED
evidence_minimality: PASS
scorecard_verdict: PASS_or_EXPLICIT_PARTIAL
same_sha_ci: GREEN
```

If any field is unknown, stale, failing, or unsupported, the final verdict cannot be `PASS`.
