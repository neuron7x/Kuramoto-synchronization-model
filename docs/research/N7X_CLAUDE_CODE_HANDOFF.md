# N7X Claude Code Handoff

Status: `DRAFT_PR_HANDOFF`
Target PR: inference transformer control plane
Scope: make the static architecture seed executable without increasing empirical claim tier.

---

## 1. Operating Contract

Claude Code must load and follow:

```text
.claude/system-prompts/N7X_COGNITIVE_ROLE_SPECIFICATION.md
```

This contract defines priority ordering, blast-radius control, deterministic execution, anti-fabrication, claim-tier discipline, context economy, tool discipline, and PARCH-FALSIFY-001.

The contract is an execution layer.
It is not empirical evidence.

Also read:

```text
docs/research/ANTHROPIC_DESIGN_STACK_ADAPTATION.md
```

That file is design context derived from operator-provided notes.
It is marked `OPERATOR_PROVIDED_SOURCE / NOT_REVERIFIED_IN_THIS_PR`.
Do not treat its external references as repository evidence unless separately retrieved and cited.

---

## 2. Current Architecture Seed

This PR defines a configuration-first typed research flow:

```text
observation -> graph_snapshot -> geometry_state -> regime_certificate -> research_artifact
```

Committed seed files:

```text
schemas/research/inference_transformer_contract.schema.json
configs/research/geosync_inference_transformer.v1.yaml
data/research/inference_transformer_blocks.v1.json
docs/research/INFERENCE_TRANSFORMER_CONTROL_PLANE.md
docs/research/INFERENCE_TRANSFORMER_IMPLEMENTATION_PLAN.md
docs/research/ANTHROPIC_DESIGN_STACK_ADAPTATION.md
.claude/commit_acceptors/inference-transformer-control-plane.yaml
.claude/system-prompts/N7X_COGNITIVE_ROLE_SPECIFICATION.md
docs/research/N7X_CLAUDE_CODE_HANDOFF.md
```

---

## 3. Implementation Objective

Convert static schema/config/data-map artifacts into a machine-verifiable contract layer.

Do not add runtime inference claims.
Do not promote any research line from `HYPOTHESIS` to `RESULT`.
Do not describe outputs as externally validated unless the repository contains evidence.

---

## 4. Required Next Files

Create these files in the next implementation PR:

```text
scripts/ci/check_inference_transformer_contract.py
tests/ci/test_inference_transformer_contract.py
src/geosync/research/transformer/contracts.py
tests/research/transformer/test_contracts.py
```

Optional if repository style supports it:

```text
src/geosync/research/transformer/__init__.py
src/geosync/research/transformer/validation.py
```

---

## 5. Contract Objects

Implement typed objects for:

```text
ObservationBlock
GraphSnapshotBlock
GeometryStateBlock
RegimeCertificateBlock
ResearchArtifactBlock
TransformerContract
```

Each object must contain:

```text
id
version
input_refs
output_refs
required_fields
failure_modes
claim_boundary
verification_gate
blast_radius
reversibility
```

---

## 6. Verification Rules

The validator must fail closed when:

```text
schema file is missing
config file is missing
data-map file is missing
block ids diverge across schema/config/data-map
required block order is changed
claim boundary is absent
verification gate is absent
unknown empirical tier is used
research artifact lacks provenance fields
blast-radius field is absent for contract mutation steps
external-source claim lacks source status
```

---

## 7. Numerical and Source Discipline

No quantitative statement may be introduced without one of:

```text
unit test
fixture
benchmark artifact
experiment registry entry
retrievable source citation
```

If none exists, mark the statement as:

```text
HYPOTHESIS
UNVERIFIED_CONTEXT
OPEN
```

External design notes are allowed only as design context.
They do not promote result status.

---

## 8. Action Gate

Before edits, classify action risk:

```text
LOW      local reads, local analysis, small feature-branch edits
MEDIUM   schemas, docs, CI config, non-destructive contract changes
HIGH     deletion, history rewrite, secret handling, release, merge, default-branch mutation
```

Low actions may proceed when requirements are clear.
Medium actions must stay scoped and documented.
High actions require explicit current authorization.

---

## 9. PARCH-FALSIFY-001 Checklist

Before commit, run this audit:

```text
P: Is the premise falsifiable?
A: Which assumption breaks first?
R: Are references real and retrievable?
C: Does the implementation match schema/config/data-map?
H: Are any filenames, metrics, APIs, model claims, or external references invented?
```

If any answer fails, do not commit the implementation as complete.

---

## 10. Local Verification Target

Minimum command target:

```bash
python -m json.tool schemas/research/inference_transformer_contract.schema.json >/dev/null
python scripts/ci/check_inference_transformer_contract.py
pytest -q tests/ci/test_inference_transformer_contract.py tests/research/transformer/test_contracts.py
```

If the repository uses a different test runner, preserve equivalent gates and document the exact command.

---

## 11. Completion Output

Claude Code must finish with:

```text
VERDICT: <RESULT | CANDIDATE | OPEN | BLOCKED>
EVIDENCE: <tests/files/commit>
NEXT: <single deterministic next action>
⊛
```

No narrative padding.
No unsupported promotion.
No implicit inheritance from prior sessions.
