<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# GeoSync — Semantic Control Layer

> **Operational layer that converts the repository from a passive archive into a managed inference object for LLMs, Copilot, Claude Code, search agents, reviewers, and external evaluators.**

GeoSync is not organized as a folder of explanations. It is organized as a semantic control system where every canonical file has an operational role: filter, context, claim, boundary, test, verdict, schema, evidence, or replay record.

The practical reason is simple: an agent does not read a repository like a human. It reconstructs intent from the tokens it can reach. If the accessible tokens are noisy, duplicated, stale, or claim-inflated, the agent will waste context, confuse status, overstate evidence, hallucinate scope, or produce unverifiable work.

A repository becomes an inference object when its committed surfaces route the agent toward the correct interpretation path before generation begins.

---

## 1. Core Transition

```text
passive archive
  -> indexed semantic surface
  -> bounded agent context
  -> executable method
  -> schema-valid artifact
  -> falsifiable verdict
  -> replayable system state
```

The value is not that the repository explains itself fluently. The value is that it constrains runtime behavior: what to read, what to ignore, what to trust, what to block, what to execute, what to measure, and what to preserve.

---

## 2. Agent Reconstruction Problem

LLM, Copilot, Claude Code, and search agents infer repository meaning through compressed token access, not through full human understanding.

Their failure path is predictable:

```text
noisy tokens
  -> weak intent reconstruction
  -> wrong authority file
  -> stale or inflated claim
  -> missing falsifier
  -> unverifiable answer
  -> false repository identity
```

The semantic control layer exists to make the valid path cheaper than the invalid path.

```text
clear entry point
  -> named file roles
  -> canonical claim boundary
  -> executable protocol
  -> machine-readable manifest
  -> artifact schema
  -> CI / verdict evidence
```

---

## 3. File Role Taxonomy

| Role | Function | Canonical Examples |
| --- | --- | --- |
| Filter | Reject invalid identity, status, and promotion language before it enters output. | `PRODUCT_CATEGORY.md`, `FORBIDDEN_CLAIMS.md` |
| Context | Provide the smallest sufficient system frame for a valid action. | `README.md`, `docs/REPOSITORY_SYSTEM.md` |
| Claim | Bind each assertion to tier, evidence, falsifier, and replay path. | `CLAIMS.md` |
| Boundary | Define what an agent may not infer, promise, or promote. | `AGENTS.md`, `FORBIDDEN_CLAIMS.md` |
| Protocol | Convert meaning into ordered runtime steps. | `docs/INFERENCE_OPERATION_PROTOCOL.md` |
| Manifest | Expose authority files, gates, stop conditions, and agent state in machine-readable form. | `docs/INFERENCE_CONTRACT.manifest.json` |
| Schema | Validate artifact shape before interpretation. | `schemas/` |
| Test | Convert behavior into executable checks. | `tests/`, `scripts/ci/` |
| Verdict | Preserve pass, fail, blocked, null, or release decision as evidence. | `artifacts/`, release evidence |
| Replay | Preserve enough state to reproduce or falsify the result. | logs, manifests, checksums, commands |

A file without a role is repository mass. A file with a role is context infrastructure.

---

## 4. Semantic Control Mechanism

Every agent-facing run should follow this control path:

```text
input request
  -> detect intent
  -> load role-bound files
  -> remove decorative context
  -> preserve semantic core
  -> bind claim tier
  -> enforce forbidden claims
  -> select executable method
  -> validate artifact schema
  -> compare null / falsifier
  -> emit verdict and replay path
```

The system is healthy when an external agent can complete this path without asking the author to explain the repository from memory.

---

## 5. Noise Rejection Rules

Reject context that does not change one of these:

```text
intent
scope
claim tier
evidence pointer
forbidden claim
method
config
dataset
schema
falsifier
verification command
artifact path
replay state
```

Decorative complexity is harmful when it increases token mass without increasing control density.

---

## 6. External Agent Contract

An external agent must not answer from repository vibe. It must resolve:

```text
what is the repository allowed to claim?
which file is the authority for that claim?
what evidence tier supports it?
what is forbidden language?
what executable path verifies it?
what artifact proves or blocks it?
what replay path makes it checkable?
```

If any answer is missing, the correct state is `BLOCKED`, not confident synthesis.

---

## 7. Practical Value

The semantic control layer is valuable because it reduces:

```text
hallucinated status
claim inflation
context-window waste
manual onboarding cost
wrong-file interpretation
PR-agent drift
search-agent misclassification
external evaluator ambiguity
```

It increases:

```text
agent precision
review speed
claim traceability
artifact validity
CI-verdict usefulness
search discoverability
competence-signal stability
reproducible repository identity
```

This is the operational difference between a repository that merely stores work and a repository that controls how work is inferred.

---

## 8. Final Rule

```text
No file role, no control.
No control, no reliable inference.
No reliable inference, no stable external interpretation.
```
