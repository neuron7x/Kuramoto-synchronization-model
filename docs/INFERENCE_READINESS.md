<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# GeoSync — Inference Readiness Contract

> **Semantic-cognitive execution boundary for when a repository, prompt system, model context, or knowledge graph stops being passive storage and becomes a controlled inference mechanism.**

Inference readiness is the transition from **stored meaning** to **runtime control**.

A repository is not inference-ready because it contains many files, diagrams, prompts, claims, benchmarks, or explanations. It becomes inference-ready only when its context architecture can accept an input, select the right semantic core, reject noise, bind claims to evidence, execute a bounded method, emit a schema-valid artifact, and preserve enough state for replay, falsification, and improvement.

The value of the system is not its description. The value is its ability to produce stable, cheap, repeatable, falsifiable results under runtime pressure.

---

## 1. First Principle

```text
A system exits to inference only when meaning becomes executable control.
```

Executable control means:

```text
context is discoverable
rules are explicit
claims are bounded
evidence is addressable
artifacts are schema-valid
failure is detectable
execution is replayable
```

A repository that only stores files is an archive.
A repository that routes meaning into bounded execution is an inference surface.

GeoSync therefore treats documentation, schemas, tests, artifacts, CI, benchmarks, and release evidence as one joined control plane. Text that does not constrain runtime behavior is not operational evidence.

---

## 2. Semantic Control Foundation

Inference readiness depends on the semantic control layer defined in [`docs/SEMANTIC_CONTROL_LAYER.md`](SEMANTIC_CONTROL_LAYER.md).

The repository enters inference only when each canonical surface has a role:

```text
filter
context
claim
boundary
protocol
manifest
schema
test
verdict
replay
```

This role binding matters because LLMs, Copilot, Claude Code, search agents, reviewers, and external evaluators do not receive the repository as a human-held memory. They reconstruct intent from reachable tokens. If those tokens are noisy, duplicated, stale, or claim-inflated, the agent can confuse status, overstate claims, waste context, or emit unverifiable output.

The valid path is therefore:

```text
role-bound file
  -> compact semantic core
  -> bounded agent action
  -> checked artifact
  -> falsifiable verdict
  -> replayable state
```

---

## 3. Semantic-Cognitive Model

Inference readiness has four cognitive layers:

| Layer | Function | Runtime Question |
| --- | --- | --- |
| Orientation | Locate the correct system frame. | What is this input asking the system to do? |
| Selection | Extract the minimum sufficient context. | Which committed facts are needed now? |
| Constraint | Bind behavior to rules, evidence, and scope. | What is the agent forbidden to infer? |
| Verification | Convert output into replayable evidence. | Can this result be checked, falsified, and repeated? |

The agent must not consume the repository as a flat text pile. It must traverse it as a semantic control graph:

```text
input intent
  -> canonical context
  -> active constraints
  -> allowed method
  -> evidence tier
  -> artifact schema
  -> falsifier
  -> replay record
```

If any edge is missing, the output is not inference. It is interpretation.

---

## 4. Runtime Mechanism

The inference-ready path is:

```text
input
  ↓
intent classification
  ↓
canonical context selection
  ↓
noise / stale-context rejection
  ↓
semantic-core preservation
  ↓
claim-boundary binding
  ↓
method and configuration selection
  ↓
deterministic execution
  ↓
null baseline / falsifier check
  ↓
schema-valid artifact emission
  ↓
replayable verification record
```

A result is admissible only when the system records enough information to repeat, measure, falsify, or improve it without manual guessing.

---

## 5. Readiness Gates

| Gate | Requirement | Blocking Condition |
| --- | --- | --- |
| File Role Binding | Canonical files are assigned operational roles: filter, context, claim, boundary, protocol, manifest, schema, test, verdict, replay. | The agent must guess why a file exists or how it constrains output. |
| Context Addressability | Canonical files are indexed, linked, and named by role. | Critical context is buried, duplicated, stale, or discoverable only by human memory. |
| Semantic Compression | Runtime context preserves the operational core while removing decorative mass. | Prompt budget is spent on prose that cannot change execution. |
| Claim Boundary | Every claim maps to tier, evidence, falsifier, and replay path. | Claim language outruns evidence tier or benchmark scope. |
| Agent Control | Agent behavior is bounded by `AGENTS.md`, forbidden claims, tests, schemas, and release rules. | Agent can invent status, scope, data, promotion level, or scientific meaning. |
| Method Binding | Each result is tied to code path, config, dataset, seed, git state, and execution command. | Output cannot be reconstructed from committed state. |
| Artifact Validity | Output conforms to machine-readable schema and durable file layout. | Result exists only as prose, screenshot, terminal memory, or chat memory. |
| Falsification | Nulls, baselines, negative controls, and failure modes are explicit. | No executable path exists to disprove the result. |
| Release Evidence | CI or local evidence bundle records commands, logs, exits, versions, checksums. | Green text exists without durable evidence. |

Promotion is blocked by any failed gate.

---

## 6. Operational Metrics

The inference surface should be measured by:

```text
file_role_coverage
context_addressability_score
context_retention_rate
context_token_waste_ratio
schema_validation_pass_rate
replay_success_rate
claim_drift_incidents
forbidden_claim_violations
null_baseline_superiority_rate
artifact_hash_coverage
agent_boundary_violation_count
manual_interpretation_dependency
external_agent_misclassification_rate
```

A system is not mature because it sounds coherent. It is mature when these measurements improve while claim inflation, prompt waste, and manual interpretation decrease.

---

## 7. Failure Modes

The repository is not inference-ready when:

```text
canonical files have no operational role
critical context is not discoverable
agent instructions conflict across files
canonical meaning is duplicated without hierarchy
outputs are not schema-bound
claims cannot be traced to evidence
evidence cannot be replayed
null baselines are absent
runtime artifacts are not reproducible
manual interpretation is required to decide validity
CI does not preserve executable evidence
```

These failures block promotion. They are not cosmetic defects.

---

## 8. GeoSync Binding

This contract binds the existing GeoSync system spine:

```text
DOCTRINE / FORBIDDEN CLAIMS
        ↓
CLAIM REGISTRY
        ↓
MACHINE-CHECKABLE INVARIANTS
        ↓
DATA CONTRACT
        ↓
SEMANTIC CONTROL LAYER
        ↓
INFERENCE CONTRACT
        ↓
NULL BASELINES / FALSIFIERS
        ↓
ARTIFACT VALIDATION
        ↓
RELEASE EVIDENCE HARNESS
        ↓
EXTERNAL REPRODUCTION
```

The inference-readiness claim is valid only when each lower layer has an explicit executable or machine-checkable witness.

---

## 9. Agent Reading Order

When an agent enters GeoSync, it should resolve context in this order:

```text
README.md
  -> docs/REPOSITORY_SYSTEM.md
  -> docs/SEMANTIC_CONTROL_LAYER.md
  -> docs/INFERENCE_READINESS.md
  -> docs/INFERENCE_OPERATION_PROTOCOL.md
  -> docs/INFERENCE_CONTRACT.manifest.json
  -> AGENTS.md
  -> forbidden-claims / doctrine files
  -> claim registry
  -> schemas
  -> tests
  -> latest release evidence
```

The agent should prefer the smallest context set that preserves correctness. More context is not better if it weakens constraint density.

---

## 10. Integral Operation Protocol

The readiness contract is executed through the seven-step operational closure in [`docs/INFERENCE_OPERATION_PROTOCOL.md`](INFERENCE_OPERATION_PROTOCOL.md) and mirrored as machine-readable control data in [`docs/INFERENCE_CONTRACT.manifest.json`](INFERENCE_CONTRACT.manifest.json):

```text
1. resolve intent
2. load canonical context
3. compress semantic core
4. bind claims to evidence
5. select executable path
6. verify and falsify
7. emit replayable artifact
```

This converts inference readiness from an architectural definition into an agent-runnable protocol. A repository surface is inference-ready only when an agent can traverse this path without inventing hidden context, weakening claim boundaries, or relying on manual interpretation.

Operational closure requires the agent to preserve:

```text
intent_type
canonical_files_used
claim_tier_before
claim_tier_after
changed_surface_type
allowed_method
blocked_claims
verification_command
evidence_artifact_path
remaining_blocker
```

If these fields cannot be resolved, the correct result is a blocked state, not a confident output.

---

## 11. Final Rule

```text
No role-bound file, no indexed context.
No indexed context, no inference.
No bounded agent, no inference.
No evidence-bound claim, no inference.
No schema-valid artifact, no inference.
No falsifier, no inference.
No replay path, no inference.
```

The transition is from:

```text
we have a system
```

to:

```text
the system performs work predictably, cheaply, measurably, and falsifiably.
```
