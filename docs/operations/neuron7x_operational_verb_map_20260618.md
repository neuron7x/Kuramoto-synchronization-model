# Neuron7X Operational Verb Map

Status: `OPERATIONS_DOCUMENTATION_ONLY`
Scope: repo-agent execution vocabulary, PR decomposition, evidence-oriented task framing.
Runtime impact: none.
Scientific claim impact: none.

## Purpose

This document converts the Neuron7X system-thinking vocabulary into an executable operations map for repository agents.

The map is not a motivational glossary. Each verb is treated as a task primitive that must produce an observable state transition, artifact, metric, gate, or decision.

Core rule:

```text
Verb -> operational intent -> action -> evidence -> checkpoint -> next action.
```

A repository agent must not use these verbs as decorative language. Every verb must either transform the repository state, validate the current state, or explicitly block unsafe action.

## Global Execution Contract

```text
1. Intention before action.
2. Measurement before optimization.
3. Validation before merge.
4. Falsification before promotion.
5. Integration before deployment.
6. Evidence before status.
7. Reverse audit after forward execution.
8. Traceability before attribution.
9. Contract before orchestration.
10. Rollback before release.
```

## Forward Execution Loop

Use this order when converting an abstract request into a pull-request sequence:

```text
інтенціювати -> дефінувати -> діагностувати -> трасувати -> інтегрувати -> операціоналізувати -> пріоритезувати -> ініціалізувати -> ізолювати -> інструментувати -> агрегувати -> нормалізувати -> канонізувати -> фільтрувати -> класифікувати -> корелювати -> атрибутувати -> валідувати -> верифікувати -> тестувати -> фальсифікувати -> профілювати -> бенчмаркнути -> калібрувати -> адаптувати -> оптимізувати -> стабілізувати -> рефакторити -> декуплювати -> інкапсулювати -> контрактувати -> оркеструвати -> синхронізувати -> логувати -> моніторити -> візуалізувати -> позиціонувати -> онбордити -> деплоїти -> релізувати -> скейлити -> ітерувати
```

## Reverse Audit Loop

Use this order after implementation to prove the result is not self-deception:

```text
ітерувати -> скейлити -> релізувати -> деплоїти -> онбордити -> позиціонувати -> візуалізувати -> моніторити -> логувати -> синхронізувати -> оркеструвати -> контрактувати -> інкапсулювати -> декуплювати -> рефакторити -> стабілізувати -> оптимізувати -> адаптувати -> калібрувати -> бенчмаркнути -> профілювати -> фальсифікувати -> тестувати -> верифікувати -> валідувати -> атрибутувати -> корелювати -> класифікувати -> фільтрувати -> канонізувати -> нормалізувати -> агрегувати -> інструментувати -> ізолювати -> ініціалізувати -> пріоритезувати -> операціоналізувати -> інтегрувати -> трасувати -> діагностувати -> дефінувати -> інтенціювати
```

The forward loop builds the solution. The reverse loop attacks it.

## Verb-to-Task Protocol

| Verb | Operational meaning | Required output |
| --- | --- | --- |
| Інтенціювати | Fix the goal, expected state, intervention boundary, risk, and stop criterion. | PR intent block, non-goals, stop rule. |
| Дефінувати | Define object, concept boundary, inclusion rule, exclusion rule, and operational sense. | Glossary entry, schema field, contract paragraph. |
| Діагностувати | Identify the observed failure, hidden cause candidates, affected layer, and uncertainty boundary. | Diagnostic report, failure class, suspected root-cause map. |
| Трасувати | Follow a claim, data item, code path, artifact, or decision back to its source. | Trace map, file/line path, provenance link. |
| Інтегрувати | Connect symptoms, data, context, constraints, and roles into one decision model. | Decision matrix, dependency map, integration summary. |
| Операціоналізувати | Convert abstract need into actions, owners, resources, metrics, and checkpoints. | Task list, ownership, acceptance gates. |
| Пріоритезувати | Rank tasks by risk, evidence gap, dependency, reversibility, and blast radius. | Priority queue, PR order, blocked/deferred list. |
| Ініціалізувати | Start module/process with explicit initial state. | Initial config, seed, baseline artifact. |
| Ізолювати | Run work separately for safety, reproducibility, or testing. | Branch, worktree, fixture, sandbox, scope boundary. |
| Інструментувати | Add measurement hooks without changing intended behavior. | Metrics, traces, counters, audit events. |
| Агрегувати | Collect related data, functions, or signals into one representation. | Inventory, manifest, evidence table. |
| Нормалізувати | Bring data, naming, format, or scale into one consistent convention. | Normalized schema, canonical path, adapter. |
| Канонізувати | Select one authoritative representation and map aliases to it. | Canonical schema, alias map, migration note. |
| Фільтрувати | Remove invalid, duplicate, stale, unsafe, or irrelevant signals. | Rejection rule, fail-closed test. |
| Класифікувати | Assign items to explicit categories with inclusion and exclusion criteria. | Taxonomy, severity class, status label. |
| Корелювати | Compare signals for co-movement without asserting causality. | Correlation table, caveat, non-causal interpretation. |
| Атрибутувати | Assign cause, ownership, or responsibility only when evidence supports it. | Causal note, owner map, confidence level. |
| Валідувати | Check whether action matches need, context, safety, goal, and use. | Validation matrix, merge/no-merge decision. |
| Верифікувати | Compare claim, data, output, or action against source, spec, protocol, or fact. | Evidence path, source mapping, reproducible check. |
| Тестувати | Simulate cases and execute assertions against behavior. | Unit/contract/integration tests. |
| Фальсифікувати | Try to disprove the hypothesis through nulls, adversarial data, and counterexamples. | Falsifier test, null baseline, demotion rule. |
| Профілювати | Characterize behavior across time, memory, performance, failure modes, and branches. | Profile report, coverage map, risk map. |
| Бенчмаркнути | Compare behavior against known baseline or reference. | Benchmark artifact, baseline delta. |
| Калібрувати | Tune thresholds, tolerances, sensitivity, or scoring against declared evidence. | Calibration table, tolerance rationale. |
| Адаптувати | Adjust model/process to new environment without violating invariants. | Compatibility patch, environment contract. |
| Оптимізувати | Improve objective under measured constraints without breaking correctness. | Metric delta, regression protection. |
| Стабілізувати | Reduce variance, flakiness, drift, or nondeterminism to a declared tolerance. | Stability report, flake fix, deterministic guard. |
| Рефакторити | Improve structure without changing external behavior. | Equivalent behavior tests, smaller interfaces. |
| Декуплювати | Remove accidental dependency between components. | Interface boundary, dependency reduction. |
| Інкапсулювати | Hide internal complexity behind stable contract. | Public API, private implementation boundary. |
| Контрактувати | Encode expectations as explicit inputs, outputs, invariants, and failure modes. | Contract file, schema, interface tests. |
| Оркеструвати | Coordinate sequence of modules, jobs, agents, or PRs. | Execution graph, ordered workflow, dependency chain. |
| Синхронізувати | Align branch state, artifacts, claims, docs, and CI against the same head. | Same-SHA gate, updated branch, sync report. |
| Логувати | Record events and decisions for traceability. | Structured logs, command log, audit trail. |
| Моніторити | Track state over time and detect drift or regression. | Status dashboard, CI watch, drift report. |
| Візуалізувати | Present structure or result so humans can audit it. | Diagram, table, rendered report. |
| Позиціонувати | State what the system is, is not, and who it serves. | Product boundary, claim boundary, README wording. |
| Онбордити | Make usage and reasoning reproducible for a new operator. | Runbook, tutorial, minimal path. |
| Деплоїти | Move verified artifact into target environment. | Deployment plan, release evidence, rollback rule. |
| Релізувати | Publish a versioned artifact only after evidence, provenance, and rollback are ready. | Release notes, manifest, tag, rollback plan. |
| Скейлити | Increase scope or throughput while preserving invariants. | Load/stress test, scaling bound, capacity metric. |
| Ітерувати | Repeat observe -> intervene -> measure -> correct until stable criterion is met. | Iteration log, convergence criterion. |

## Missing-Layer Additions

The original uploaded vocabulary already covered architecture, AI logic, validation, infrastructure, and medical-style operational commands. The repo-execution layer needs additional verbs because repository work fails less from missing ideas than from missing control surfaces. Delightful, apparently software needs a nervous system too.

| Verb | Why it was added | Required guard |
| --- | --- | --- |
| Діагностувати | Prevents acting on symptoms without a failure model. | Diagnostic classification before patch. |
| Трасувати | Prevents claims, artifacts, and fixes from becoming untraceable folklore. | Source/provenance path before status. |
| Пріоритезувати | Prevents large mixed PRs and dependency inversion. | Risk-ranked PR order. |
| Інструментувати | Makes invisible behavior measurable. | Metrics without semantic mutation. |
| Канонізувати | Converts duplicate contracts into one authority. | Canonical path plus alias map. |
| Класифікувати | Converts vague states into decision categories. | Explicit enum or severity matrix. |
| Корелювати | Allows pattern detection without false causality. | Non-causal caveat. |
| Атрибутувати | Assigns cause or owner only with evidence. | Confidence level and trace. |
| Стабілізувати | Targets nondeterminism and flaky gates. | Variance/flakiness criterion. |
| Контрактувати | Converts expectations into enforceable boundaries. | Schema/interface/invariant tests. |
| Синхронізувати | Ensures docs, artifacts, CI, and branch head refer to the same state. | Same-SHA verification. |
| Релізувати | Separates deployable intent from evidence-bearing publication. | Manifest, provenance, rollback. |
| Карантинувати | Isolates unsafe claims, files, or tests without deleting evidence. | Quarantine reason, owner, expiry. |
| Демотувати | Lowers unsupported claims without deleting history. | Claim-tier change with evidence gap. |
| Ескалювати | Moves unresolved risk to a higher control lane. | Escalation reason and blocking condition. |
| Ролбекнути | Restores last known valid state when a change violates a gate. | Rollback command and target SHA. |
| Атестувати | Certifies that artifact provenance and checksums match expected state. | Attestation/provenance record. |
| Архівувати | Preserves obsolete evidence, decisions, or failed attempts for audit. | Archive path and retention note. |

## Repository-Control Verbs

These verbs must be used when operating pull requests and release evidence.

| Verb | Operational meaning | Required output |
| --- | --- | --- |
| Карантинувати | Isolate unsafe or incomplete work from merge paths while preserving evidence. | Quarantine registry entry, expiry, unblock condition. |
| Демотувати | Lower claim status when evidence is absent, weak, stale, or contradicted. | Claim-tier diff, reason, replacement status. |
| Ескалювати | Promote a risk to a blocking lane when local resolution is unsafe. | Blocking issue, owner, dependency link. |
| Ролбекнути | Return to a last known good state after failed validation or unsafe merge. | Revert/rollback SHA, verification run. |
| Атестувати | Bind artifact identity to checksum, provenance, commit, and environment. | Attestation, SBOM/provenance path. |
| Архівувати | Preserve superseded evidence, failed runs, or retired claims without treating them as active. | Archive manifest, retention note. |

## Pull Request Decomposition Rules

A PR must map to one dominant verb and at most two supporting verbs.

Examples:

```text
PR type: validation
Dominant verb: Валідувати
Supporting verbs: Верифікувати, Фальсифікувати
Expected files: tests/, scripts/ci/, artifacts/audit/
Forbidden scope: runtime behavior rewrite without failing test.
```

```text
PR type: documentation/operations
Dominant verb: Операціоналізувати
Supporting verbs: Дефінувати, Інтегрувати
Expected files: docs/operations/, docs/contracts/
Forbidden scope: code semantics, product claim promotion.
```

```text
PR type: core hardening
Dominant verb: Фальсифікувати
Supporting verbs: Тестувати, Верифікувати
Expected files: tests/core/, core/ only if failing test proves bug.
Forbidden scope: cosmetic refactor mixed with numerical behavior change.
```

```text
PR type: canonicalization
Dominant verb: Канонізувати
Supporting verbs: Трасувати, Контрактувати
Expected files: schemas/, docs/contracts/, tests/schemas/
Forbidden scope: duplicate contract creation without alias mapping.
```

```text
PR type: release evidence
Dominant verb: Атестувати
Supporting verbs: Релізувати, Ролбекнути
Expected files: artifacts/evidence_bundle/, release notes, provenance/SBOM paths.
Forbidden scope: release status without manifest verification.
```

## Merge Readiness Rule

A PR is not ready because its story is coherent. A PR is ready only when its dominant verb has evidence:

```text
Валідувати -> validation matrix exists.
Верифікувати -> source/spec/fact mapping exists.
Фальсифікувати -> failing-condition test exists.
Операціоналізувати -> roles/actions/metrics/checkpoints exist.
Інтегрувати -> symptoms/data/context/constraints/roles are connected.
Ітерувати -> next loop and stop criterion are explicit.
Діагностувати -> failure class and suspected root cause exist.
Трасувати -> provenance/source path exists.
Канонізувати -> canonical representation and alias map exist.
Контрактувати -> explicit invariant/schema/interface exists.
Синхронізувати -> same-head evidence exists.
Карантинувати -> unblock condition and expiry exist.
Демотувати -> unsupported claim is lowered with reason.
Ролбекнути -> rollback target and verification command exist.
Атестувати -> provenance/checksum evidence exists.
```

## Execution Acts of Work

This section closes the operational run as an auditable work act. It records what this document is allowed to claim, what it is not allowed to claim, and which evidence gates must exist before the work is treated as complete.

### Act 1 — Vocabulary-to-Operation Conversion

| Field | Value |
| --- | --- |
| Operational need | Convert an uploaded system-thinking vocabulary into a repo-executable agent protocol. |
| Dominant verb | Операціоналізувати. |
| Supporting verbs | Дефінувати, Інтегрувати, Валідувати, Верифікувати. |
| Performed action | Mapped each cognitive/technical verb to an operational meaning and required repository output. |
| Evidence form | This document, PR metadata, same-head CI result, and docs-only diff scope. |
| Acceptance condition | Every verb must produce an observable state transition, artifact, metric, gate, or decision. |
| Boundary | No runtime implementation, scientific claim, model behavior, or CI policy is changed. |

Argumentation: the uploaded vocabulary is useful only if it stops being a passive glossary. Repository agents require action semantics: intent, action, evidence, checkpoint, and next action. The conversion is valid because it binds language to observable repository states instead of allowing agent prose to masquerade as execution.

### Act 2 — Missing Control-Layer Completion

| Field | Value |
| --- | --- |
| Operational need | Add the verbs missing from the original vocabulary for safe repository execution. |
| Added control layer | diagnosis, traceability, prioritization, instrumentation, canonicalization, classification, attribution, stabilization, contract, synchronization, quarantine, demotion, escalation, rollback, attestation, archival. |
| Risk addressed | Untraceable claims, duplicate contracts, mixed PRs, unsafe merge paths, non-reproducible releases, and status inflation. |
| Acceptance condition | Each added verb must include a guard that prevents narrative-only completion. |
| Boundary | The additions govern execution behavior; they do not promote product, scientific, or performance claims. |

Argumentation: repository failure usually does not begin with missing intelligence; it begins with missing control surfaces. A system that can integrate but cannot rollback, trace, demote, quarantine, or attest is not operationally mature. It is just eloquent fragility with commit access, a terrifyingly common species.

### Act 3 — Forward and Reverse Execution Closure

| Field | Value |
| --- | --- |
| Operational need | Force agents to execute and then audit their execution in reverse. |
| Forward loop | Builds the solution through intention, definition, diagnosis, integration, operation, validation, testing, release, and iteration. |
| Reverse loop | Attacks the solution from iteration back to intention to expose hidden gaps. |
| Acceptance condition | A completed task must survive both forward execution and reverse audit. |
| Boundary | Reverse audit is not optional commentary; it is the contradiction check for the forward chain. |

Argumentation: forward execution alone proves only that an agent can produce movement. Reverse audit proves whether the movement was coherent, bounded, and evidence-bearing. This is the minimum adult supervision for autonomous repo work. Apparently software needs reverse digestion too.

### Act 4 — PR Decomposition and Merge Readiness

| Field | Value |
| --- | --- |
| Operational need | Prevent large, mixed, ambiguous PRs that blend documentation, runtime behavior, claims, and evidence. |
| Rule | One dominant verb per PR, at most two supporting verbs. |
| Merge readiness | A PR is ready only when the dominant verb has its required evidence. |
| Acceptance condition | Same-head CI, clear scope, no forbidden claim promotion, no unresolved blocker, and explicit rollback path where relevant. |
| Boundary | A coherent PR story is not evidence. CI and artifacts are evidence. Charming narratives can wait outside. |

Argumentation: the rule reduces blast radius and makes review tractable. It also prevents agents from hiding risky runtime changes inside documentation or claim updates. The result is not bureaucratic overhead; it is operational containment.

### Act 5 — Evidence and Status Discipline

| Field | Value |
| --- | --- |
| Operational need | Prevent status inflation after documentation-only work. |
| Allowed status | `OPERATIONS_DOCUMENTATION_ONLY`. |
| Forbidden status | product readiness, scientific validation, performance improvement, runtime hardening, or claim-tier promotion. |
| Acceptance condition | The PR may be merged only as an operations documentation artifact. |
| Boundary | The document can guide future execution; it does not prove that future execution has already occurred. |

Argumentation: a protocol is not the same thing as execution. This document improves the command grammar of future agents; it does not validate any physics kernel, data contract, or release artifact by itself. That distinction is the difference between governance and decorative confidence.

## Final Acceptance Act

```text
VERB_APPLIED: Операціоналізувати
INTENT: Convert a cognitive vocabulary into a repository execution protocol.
ACTIONS: Defined task primitives, forward loop, reverse audit loop, PR decomposition rules, merge readiness rules, and repository-control verbs.
EVIDENCE: Single docs-only operations file, PR diff scope, same-head CI requirement, no runtime changes.
CHECKPOINTS: docs consistency, claim boundary, PR gate, commit acceptor, repo integrity.
BLOCKERS: Any failed same-head CI, forbidden claim promotion, runtime mutation, or unresolved review blocker.
REVERSE_AUDIT: Every verb must map back to intent, evidence, checkpoint, and stop rule.
NEXT_VERB: Верифікувати through CI and merge metadata.
FINAL_STATUS: OPERATIONS_DOCUMENTATION_READY_WHEN_SAME_HEAD_CI_GREEN.
```

## Agent Final Response Format

Every agent executing this map must return:

```text
VERB_APPLIED:
INTENT:
ACTIONS:
EVIDENCE:
CHECKPOINTS:
BLOCKERS:
REVERSE_AUDIT:
NEXT_VERB:
FINAL_STATUS:
```

For repository-control verbs, also return:

```text
CLAIM_OR_ARTIFACT_IMPACT:
SAME_HEAD_STATUS:
ROLLBACK_PATH:
TRACE_PATH:
```

## Stop Rule

Stop if the action cannot be tied to evidence, test, artifact, or decision. Do not continue by inventing prose. The repository does not need decorative cognition; it needs observable state transitions.
