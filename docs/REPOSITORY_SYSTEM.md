<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# GeoSync — Repository System

> **Operational map for the repository as a verification-first quantitative research system.**

This document is the compact spine for reviewers, collaborators, auditors, and future implementation agents. It explains what the repository is allowed to claim, which surfaces are canonical, how evidence moves through the system, and where a result must stop when proof is incomplete.

GeoSync is organized around one rule:

> **A research statement is admissible only when its invariant, data source, method, artifact, falsifier, and replay path are explicit.**

The repository is not optimized for persuasive language. It is optimized for controlled promotion of claims under machine-checkable boundaries.

---

## 1. Canonical Surfaces

| Surface | Role |
| --- | --- |
| [`README.md`](../README.md) | Public entry point and high-level system narrative. |
| [`PRODUCT_CATEGORY.md`](../PRODUCT_CATEGORY.md) | Canonical product-category boundary. Defines what GeoSync is and is not. |
| [`CLAIMS.md`](../CLAIMS.md) | Single source of truth for claim tiers and evidence pointers. |
| [`FORBIDDEN_CLAIMS.md`](../FORBIDDEN_CLAIMS.md) | Status-language firewall and promotion invariants. |
| [`AGENTS.md`](../AGENTS.md) | Root implementation contract for Claude, Codex, and automation agents. |
| [`docs/PR_PREFLIGHT_RUNBOOK.md`](PR_PREFLIGHT_RUNBOOK.md) | Operational contract for the structured local PR preflight runner and its evidence report. |
| [`docs/SEMANTIC_CONTROL_LAYER.md`](SEMANTIC_CONTROL_LAYER.md) | File-role taxonomy and semantic-control model for external LLM, Copilot, Claude Code, search, reviewer, and evaluation agents. |
| [`docs/INFERENCE_READINESS.md`](INFERENCE_READINESS.md) | Runtime-readiness contract for context architecture, agent boundaries, artifact validity, and falsification control. |
| [`docs/INFERENCE_OPERATION_PROTOCOL.md`](INFERENCE_OPERATION_PROTOCOL.md) | Seven-step runbook for converting repository meaning into bounded, replayable, falsifiable execution. |
| [`docs/INFERENCE_CONTRACT.manifest.json`](INFERENCE_CONTRACT.manifest.json) | Machine-readable control manifest for authority files, reading order, gates, stop conditions, and required agent state. |
| [`docs/MFN_VERIFICATION_ROADMAP.json`](MFN_VERIFICATION_ROADMAP.json) | MFN gateway machine-readable verification roadmap contract. |
| [`BASELINE.md`](../BASELINE.md) | Baseline evidence and comparison reference when present. |
| [`schemas/`](../schemas) | Machine-readable contracts for artifacts and governance records. |
| [`scripts/ci/`](../scripts/ci) | Enforcement scripts for claim boundary, gates, and release discipline. |
| [`artifacts/`](../artifacts) | Generated or committed evidence surfaces. Placeholder artifacts must identify themselves as placeholders. |

All other documents must conform to these surfaces. New text that upgrades a claim without updating `CLAIMS.md` is drift.

---

## 2. System Layers

```text
L0  Doctrine / boundary language
L1  Claim registry / evidence tier
L2  Data contract / immutable hashes
L3  Semantic control layer / file-role routing
L4  Inference readiness / semantic control graph
L5  Inference operation protocol / seven-step runtime
L6  Inference method / deterministic transform
L7  Nulls / falsifiers / alternative hypotheses
L8  Artifact schema / validation
L9  CI gate / release evidence
L10 External reproduction capsule
```

A layer may depend only on validated lower layers. A higher layer cannot repair a broken lower layer by sounding confident. Human civilization keeps trying this. GeoSync does not.

---

## 3. Claim Promotion Automaton

```text
IDEA
  ↓
HYPOTHESIS
  ↓
PREREGISTERED
  ↓
INSTRUMENTED
  ↓
TESTED_SYNTHETIC
  ↓
TESTED_REAL_SINGLE
  ↓
TESTED_REAL_MULTI
  ↓
MEASURED
  ↓
REPLICATED
```

Allowed terminal or blocking states:

```text
REJECTED
BLOCKED_DATA
BLOCKED_REPRO
BLOCKED_NULL
BLOCKED_COST_MODEL
RETIRED
```

A failed result is not removed. It is recorded, classified, and preserved. Silent deletion is not epistemology; it is cosmetic damage control.

---

## 4. Evidence-Bearing Artifact Requirements

A result may support promotion only when the artifact records:

```text
run_id
git_sha
git_dirty
data_sha256
config_sha256
seed
timestamp_utc
method_version
score
score_source
uncertainty
baseline
falsification_status
decision
claim_tier
artifact_role
replay_command
```

Minimum rule:

```text
score_source must be computed
artifact_role must not be placeholder
falsification_status must not be NOT_RUN
baseline must be explicit
replay_command must execute the same artifact path
```

Schema validity proves shape. It does not prove truth.

---

## 5. Semantic Control Boundary

GeoSync is a managed inference object only when each canonical file has a runtime role:

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

The detailed role taxonomy is defined in [`docs/SEMANTIC_CONTROL_LAYER.md`](SEMANTIC_CONTROL_LAYER.md). A file that does not constrain intent, scope, claim tier, method, schema, falsifier, or replay state is repository mass, not operational context.

This boundary exists because external agents reconstruct repository intent from reachable tokens. If the token surface is noisy or unbounded, the repository identity becomes guesswork.

---

## 6. Inference Operation Boundary

Inference readiness becomes operational only when the agent can traverse the committed seven-step path:

```text
resolve intent
  -> load canonical context
  -> compress semantic core
  -> bind claims to evidence
  -> select executable path
  -> verify and falsify
  -> emit replayable artifact
```

The machine-readable mirror is [`docs/INFERENCE_CONTRACT.manifest.json`](INFERENCE_CONTRACT.manifest.json). The human-readable runbook is [`docs/INFERENCE_OPERATION_PROTOCOL.md`](INFERENCE_OPERATION_PROTOCOL.md).

Minimum required agent state:

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

If the agent cannot resolve this state, it must return a blocked result instead of inventing context.

---

## 7. Ricci Microstructure Boundary

The active line is:

```text
ricci_microstructure_v1
```

Current admissible state:

```text
HYPOTHESIS
INSTRUMENTED
NOT EVIDENCE-BEARING
```

The repository may describe the computation path and provenance instrumentation. It must not describe the line as measured, predictive, externally replicated, or deployment-ready until qualifying real-data artifacts pass the declared gates.

Current implementation boundary:

```text
src/geosync/features/ricci.py::RicciCurvatureGraph.fit_transform
```

This supports graph-level structural computation. It does not by itself establish market-mechanism truth.

---

## 8. MFN Gateway Boundary

The MFN path is a dependency-light operational gateway:

```text
simulate → extract → detect → forecast → compare → report
```

Its job is to prove:

```text
packaging
console entrypoints
dependency-light execution
artifact bundle shape
hash-manifest discipline
local reproducibility
```

It may produce `INSTRUMENTED` artifacts. It may not promote a research statement beyond its evidence tier.

## 9. Reviewer Protocol

A reviewer inspects the repository in a fixed order so that nothing claim-bearing is accepted on impression:

```text
1. PRODUCT_CATEGORY.md — is the claim inside the allowed category?
2. CLAIMS.md / FORBIDDEN_CLAIMS.md — is the tier honest, the wording permitted?
3. invariant + data + method + artifact + falsifier + replay — all six present?
4. replay command succeeds on a clean checkout (not "looks right").
5. AGENTS.md — did the change follow the implementation-agent contract?
```

A green terminal line is an observation; a reviewer accepts only a replayable artifact.

## 10. Definition of Repository Completion

The repository is complete for a claim only when every leg below holds, and not before:

```text
- the claim sits at an honest tier in CLAIMS.md
- a falsifier exists and a reviewer can run it
- the replay command succeeds from a clean checkout
- retired or failed states are preserved (RETIRED, never silently deleted)
- no FORBIDDEN_CLAIMS.md status-language leaks into the public surface
```

Incomplete proof stops at the boundary; it does not promote.

---
