<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# GeoSync — Inference Operation Protocol

> **Seven-step operational protocol for converting repository meaning into bounded, replayable, falsifiable agent execution.**

This document is not a narrative explanation. It is a runbook for agents, reviewers, and automation systems that enter GeoSync and must decide what to read, what to ignore, what to execute, what to block, and what evidence must remain after the run.

The protocol exists because an inference-ready repository is not a file pile. It is a semantic execution surface.

---

## 0. Prime Rule

```text
Only role-bound meaning that changes execution is operational context.
```

A token is useful only when it constrains one of the following:

```text
intent
scope
file role
claim tier
method
config
data
artifact schema
falsifier
replay path
promotion boundary
```

Everything else is decorative mass unless it improves addressability, verification, or reproducibility.

The file-role taxonomy is defined in [`docs/SEMANTIC_CONTROL_LAYER.md`](SEMANTIC_CONTROL_LAYER.md): filter, context, claim, boundary, protocol, manifest, schema, test, verdict, replay.

---

## 1. Seven-Step Integral Runtime

```text
1. resolve intent
2. load role-bound canonical context
3. compress semantic core
4. bind claims to evidence
5. select executable path
6. verify and falsify
7. emit replayable artifact
```

The steps are sequential. A later step cannot repair a broken earlier step.

---

## 2. Step Contract

| Step | Operation | Output | Blocker |
| --- | --- | --- | --- |
| 1. Resolve Intent | Classify the request as documentation, schema, gate, artifact, code, benchmark, release, or claim-status change. | `intent_record` | The request implies promotion but does not name evidence. |
| 2. Load Role-Bound Canonical Context | Read the smallest authority set needed for the intent and preserve each file role. | `context_set`, `file_roles_used` | The required authority file is missing, stale, contradicted, or role-ambiguous. |
| 3. Compress Semantic Core | Remove prose that does not constrain execution; preserve invariants, boundaries, commands, hashes, schemas, and falsifiers. | `semantic_core` | Critical meaning depends on human memory or chat-only context. |
| 4. Bind Claims to Evidence | Attach every claim to tier, evidence pointer, falsifier, and replay path. | `claim_binding` | Claim language outruns committed evidence. |
| 5. Select Executable Path | Choose method, config, dataset, schema, command, and artifact target. | `execution_plan` | No deterministic command or schema exists. |
| 6. Verify and Falsify | Run or define the admissible verification path: tests, schema validation, null baseline, cost model, replay check. | `verification_record` | Nulls are absent, schema fails, or replay is impossible. |
| 7. Emit Replayable Artifact | Persist result, decision, evidence, logs, checksums, git state, and remaining blockers. | `evidence_artifact` | Result exists only as prose, screenshot, memory, or terminal impression. |

---

## 3. Cognitive Load Rule

The agent must treat repository context as a control graph, not as a long document:

```text
user intent
  -> role-bound authority file
  -> active invariant
  -> evidence tier
  -> method boundary
  -> artifact schema
  -> falsifier
  -> replay command
```

Context is complete when the next valid action is determined. Context is excessive when it increases explanation without increasing control.

---

## 4. Authority Resolution Order

For public claim, research status, or repository identity changes:

```text
PRODUCT_CATEGORY.md
  -> FORBIDDEN_CLAIMS.md
  -> CLAIMS.md
  -> README.md
  -> docs/REPOSITORY_SYSTEM.md
  -> docs/SEMANTIC_CONTROL_LAYER.md
  -> docs/INFERENCE_READINESS.md
  -> docs/INFERENCE_OPERATION_PROTOCOL.md
  -> docs/INFERENCE_CONTRACT.manifest.json
  -> AGENTS.md
  -> schemas/
  -> scripts/ci/
  -> artifacts/
```

For code-only changes, the agent may narrow the path, but it must still preserve claim boundaries, file roles, and release evidence rules.

---

## 5. Required Agent State

Before producing an answer, commit, PR, or artifact, an implementation agent must be able to state:

```text
intent_type
canonical_files_used
file_roles_used
claim_tier_before
claim_tier_after
changed_surface_type
allowed_method
blocked_claims
verification_command
evidence_artifact_path
remaining_blocker
```

If these fields cannot be resolved, the action is not ready for inference output.

---

## 6. Runtime Stop Conditions

Stop or block promotion when:

```text
file role is ambiguous
claim has no tier
claim has tier but no evidence
artifact has evidence but no schema
schema passes but replay path is absent
replay path exists but falsifier is absent
null baseline is not recorded
result requires manual interpretation to decide validity
agent must invent missing context
```

A blocked result is still useful if it is classified and preserved.

---

## 7. Output Shape

Every operational completion should report:

```text
changed_files
commit_sha
intent_type
file_roles_used
claim_tier_impact
verification_command
evidence_artifact_path
blocked_claims
remaining_blocker
```

Do not report maturity, alpha, predictive value, deployment readiness, or scientific proof unless the committed evidence tier permits it.

---

## 8. Final Closure

```text
Inference is not fluent explanation.
Inference is controlled transition:
input -> role-bound context -> deterministic method -> checked artifact -> falsifiable replay.
```
