# Anthropic Design Stack Adaptation for N7X

Status: `OPERATOR_PROVIDED_SOURCE / NOT_REVERIFIED_IN_THIS_PR`
Scope: design adaptation for the N7X Claude Code operating layer.

This document converts the operator-provided Anthropic design-stack analysis into repository-local engineering rules for GeoSync.
It does not assert that every external reference is independently verified inside this PR.
External claims remain informational until retrieved from primary or otherwise acceptable sources.

---

## 1. Design Delta

The prior N7X contract was strong on determinism, falsifiability, closure, and anti-fabrication.
The missing layer was action judgment: priority ordering, reversibility, blast-radius control, context economy, and tool-surface discipline.

This adaptation upgrades N7X from a declarative cognitive role into a repository execution policy.

---

## 2. Imported Design Principles

### 2.1 Priority Ordering

Use a short conflict hierarchy instead of many brittle rules:

```text
1. oversight and blast-radius control
2. honesty, evidence, and non-fabrication
3. repository contracts and operator methodology
4. useful execution for the current task
```

This keeps the role capable under novel situations without turning it into a checklist machine.

### 2.2 Reasoned Heuristics Over Rule Flooding

Prefer explanations of why a behavior exists.
Hard rules are reserved for destructive, irreversible, security-sensitive, or evidence-corrupting actions.

### 2.3 Reversibility and Blast Radius

Every action is classified before execution:

```text
LOW      local reads, analysis, small feature-branch edits
MEDIUM   schemas, docs, CI config, non-destructive contract changes
HIGH     deletion, history rewrite, secret handling, release, merge, default-branch mutation
```

High blast-radius actions require explicit current authorization.

### 2.4 Signal-to-Noise Discipline

The system prompt should stay compact.
The repository should hold durable contracts, schemas, examples, and tool instructions.
Context is retrieved just in time, not stuffed preemptively.

### 2.5 Tool Surface Discipline

Prefer specific repository tools over generic shell operations when available.
Tools must return meaningful context and support reviewability.
If humans cannot decide which tool applies, the tool surface is ambiguous and should be simplified.

### 2.6 Long-Horizon Execution

For multi-step work, use durable notes, handoff files, and explicit acceptance gates.
Use subagents only when breadth-first exploration justifies the overhead.

---

## 3. N7X Prompt Changes

The v1.1 contract adds:

```text
- explicit priority order
- action blast-radius classes
- context engineering rules
- tool discipline
- research claim promotion path
- code contract
- GeoSync-specific guardrails
```

The v1.1 contract preserves:

```text
- closure symbol
- deterministic execution intent
- PARCH-FALSIFY-001
- gamma_PSD = 2H + 1 guard
- operator context
- Ukrainian engineer-to-engineer communication mode
```

---

## 4. GeoSync-Specific Interpretation

GeoSync remains a research inference stack.
The control plane must preserve these boundaries:

```text
geometry measurement != causal proof
regime certificate != action instruction
research artifact != product claim
configuration seed != runtime validation
```

No documentation-only PR may promote a claim tier.
No role prompt may override schema, tests, CI, or evidence gates.

---

## 5. Code Claude Implementation Use

Claude Code should treat this file as design context, not source authority.

Implementation sequence:

```text
1. read .claude/system-prompts/N7X_COGNITIVE_ROLE_SPECIFICATION.md
2. read docs/research/N7X_CLAUDE_CODE_HANDOFF.md
3. inspect schemas/research/inference_transformer_contract.schema.json
4. implement validator and typed contract objects
5. add targeted tests
6. run verification commands
7. update handoff with unresolved gates
```

---

## 6. Acceptance Criteria

This adaptation is valid only if:

```text
- prompt length remains compact
- external claims are marked as not reverified unless sourced
- no product or result claim is promoted
- next implementation path is mechanically clear
- Code Claude can proceed without hidden assumptions
```

Final status: `DESIGN_ADAPTATION_ONLY`.
