# Deployment Runtime Protocol — Active GeoSync Closure System

## 0. Definition

To deploy the closure system means to move the operational protocol from static documentation into the repository execution environment where agents, pull requests, CI gates, ledgers, and scorecards must obey it.

This is not product deployment.

This is governance-runtime deployment.

The deployable system is the closure control plane:

- first-principles closure standard;
- operational closure protocol;
- Metrics v2;
- cognitive and definition gates;
- behavioral anti-fake-green program;
- architecture impossibility principle;
- verification axiom;
- visual execution map;
- agent prompt protocol.

## 1. Deployment Intent

Deploy the closure standard so that Code Claude and any future agent treat it as the active execution contract for closing GeoSync physics, governance, UI/E2E, and ledger lanes.

The intended state is not “the documents exist.”

The intended state is:

- agents load the protocol before acting;
- PR closure follows the declared role, metric, checkpoint, and stop-rule model;
- fake-green states are rejected;
- runtime evidence is required before closure;
- ledger state is synchronized after merges;
- final verdicts are computed from gates, not written as persuasion.

## 2. Deployment Boundary

Allowed deployment scope:

- repository documentation under `docs/operations/`;
- PR body references;
- agent prompt usage;
- CI/ledger/scorecard follow-up PRs;
- review comments that enforce this protocol;
- future automation that reads these docs as policy inputs.

Forbidden deployment scope in this PR:

- production system deployment;
- secret handling;
- cloud infrastructure changes;
- trading runtime activation;
- workflow gate mutation;
- source-code behavior changes;
- auto-merge activation;
- bypassing branch protection.

## 3. Deployment Targets

### Target A — Human/Agent Reading Layer

Location:

- PR #1157;
- `docs/operations/`.

Purpose:

- provide the canonical execution packet.

Deployment condition:

- all operation documents are linked from the PR body;
- the agent prompt protocol names the required read order;
- no older protocol contradicts the current one.

### Target B — PR Execution Layer

Location:

- active PRs such as #1153, #1155, #1154, #1150, #1152, #1147.

Purpose:

- enforce the execution order and stop rules.

Deployment condition:

- no dependent PR is merged before #1153 terminal state or explicit quarantine;
- each PR reports owner, metric, checkpoint, evidence, risk, and stop criterion;
- every closure claim has a same-SHA witness.

### Target C — CI Measurement Layer

Location:

- GitHub Actions;
- fast shard;
- heavy validation lanes;
- status checks.

Purpose:

- convert CI from badge output into measurement instrument.

Deployment condition:

- no shard can pass from 0/0 collection;
- collection count is visible;
- stale SHA cannot justify merge;
- failures are classified, fixed, or quarantined with owner and expiry.

### Target D — Ledger and Scorecard Layer

Location:

- audit ledger JSON;
- audit markdown;
- scorecard JSON;
- verdict documents.

Purpose:

- make repository truth state machine-readable.

Deployment condition:

- every resolved claim has a resolution reference;
- merged PRs are not left as IN_PROGRESS;
- final verdict cannot be PASS while required metrics are OPEN, UNKNOWN, or STALE.

## 4. Deployment Sequence

Phase 1: Stage

- keep #1157 as draft;
- ensure operation documents are complete;
- ensure PR body lists the deployment contract;
- do not merge #1157 as runtime policy yet.

Phase 2: Bind

- Code Claude loads #1157 before touching active lanes;
- each active PR receives a Section 17 style output;
- task owners follow role boundaries;
- #1153 remains the first terminalization target.

Phase 3: Exercise

- run the protocol against one active lane;
- preferred lane: #1153, because it owns the measurement instrument;
- verify that the protocol changes action selection, not just wording.

Phase 4: Promote

- once the protocol has guided at least one real terminal transition, mark #1157 ready for review;
- keep it draft if it remains only descriptive;
- do not promote if agents ignored the stop rules.

Phase 5: Enforce

- convert selected protocol rules into tests, acceptors, or CI checks through follow-up PRs;
- do not pretend documentation alone is enforcement;
- every future enforcement PR must name the protocol section it operationalizes.

## 5. Deployment Readiness Metrics

### metric_deployment_readiness

Owner:

- Repository Closure Cognitive Operator.

Source of truth:

- PR #1157 file list;
- PR body;
- active PR behavior;
- CI state after #1153.

Target:

- protocol is referenced, loaded, exercised, and converted into at least one verified transition.

Partial:

- protocol exists and is referenced, but no active lane has been closed through it.

Fail:

- protocol exists only as documentation and does not affect agent behavior.

### metric_runtime_binding

Target:

- at least one rule from #1157 becomes executable in CI, tests, ledger, acceptor, or review gate.

Partial:

- rule is used manually by Code Claude but not executable yet.

Fail:

- rule is only prose.

### metric_deployment_safety

Target:

- no production, secret, trading, or infrastructure side effect occurs from this PR.

Fail:

- #1157 mutates runtime behavior directly.

### metric_protocol_adoption

Target:

- active PR output includes role, intent, expected state, boundary, metric, checkpoint, risk, stop criterion, and verdict.

Fail:

- active PR output returns motivational summary or unverifiable status.

## 6. Deployment Stop Rules

Stop deployment if:

- #1157 tries to modify runtime behavior directly;
- active PRs continue merging on old fake-green semantics;
- #1153 remains unresolved and dependent lanes are still promoted;
- Code Claude produces reports instead of state transitions;
- ledger and scorecard do not reflect merged reality;
- PR body and operation files diverge.

## 7. Rollback Model

Rollback does not mean deleting the idea.

Rollback means demoting deployment stage:

- from Enforce back to Promote;
- from Promote back to Exercise;
- from Exercise back to Bind;
- from Bind back to Stage.

A rollback is required when the protocol creates friction without improving evidence quality.

A rollback is not required merely because it blocks premature merging.

Blocking premature merging is the point.

## 8. Deployment Evidence Packet

After deployment exercise, the agent must produce:

- protocol version used;
- active PR targeted;
- action selected because of the protocol;
- action rejected because of the protocol;
- metric changed;
- CI or ledger witness;
- residual risk;
- next enforcement candidate.

## 9. Final Deployment Verdict

Allowed verdicts:

- NOT_DEPLOYED: documentation exists but is not used.
- STAGED: protocol is present in #1157.
- BOUND: agent loads and follows it.
- EXERCISED: protocol changed one real PR action.
- ENFORCED: at least one rule is executable by CI/test/acceptor/ledger.
- RETIRED: protocol was superseded by stronger automation.

Current intended status for #1157:

STAGED → BOUND.

It must not be called ENFORCED until repository automation executes at least one rule without relying on human memory.

## 10. Deployment Axiom

A protocol is not deployed when it is written.

A protocol is deployed when it constrains behavior in the execution environment.

If the system can still produce the forbidden state without resistance, deployment has not happened.
