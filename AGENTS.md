<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# AGENTS.md — GeoSync Implementation Contract

This repository is a verification-first quantitative research system. Agents must optimize for evidence, reproducibility, and claim discipline, not cosmetic confidence.

## Prime Directive

Before changing code or documentation, preserve the claim boundary:

```text
No new claim without tier.
No tier upgrade without evidence.
No evidence without artifact.
No artifact without schema.
No schema pass without replay.
No release without evidence bundle.
```

## Canonical Files

Read these before modifying public-facing text, gates, schemas, artifacts, or research-line status:

```text
README.md
PRODUCT_CATEGORY.md
CLAIMS.md
FORBIDDEN_CLAIMS.md
docs/REPOSITORY_SYSTEM.md
docs/governance/AUTONOMOUS_AGENT_EXECUTION_PROTOCOL.md
docs/SEMANTIC_CONTROL_LAYER.md
docs/INFERENCE_READINESS.md
docs/INFERENCE_OPERATION_PROTOCOL.md
docs/INFERENCE_CONTRACT.manifest.json
schemas/
scripts/ci/
```

`PRODUCT_CATEGORY.md`, `CLAIMS.md`, and `FORBIDDEN_CLAIMS.md` are authority files. Do not contradict them from another document. That would be less “agentic intelligence” and more “autocomplete with ambition.”

## Required Behavior

Agents must:

```text
1. Identify the exact research line or subsystem being changed.
2. State whether the change is documentation, schema, gate, artifact, code, or release evidence.
3. Classify the role of every changed canonical surface: filter, context, claim, boundary, protocol, manifest, schema, test, verdict, or replay.
4. Preserve existing evidence tiers unless qualifying artifacts justify promotion.
5. Keep placeholder artifacts explicitly marked as placeholders.
6. Add or update validation when introducing new contract fields.
7. Leave a deterministic command that verifies the modified surface.
8. Prefer minimal coherent changes over broad rewrites.
9. Preserve failed, blocked, retired, or negative results when they carry evidence value.
10. Follow the inference operation protocol before emitting a final result.
```

## Inference Operation Rule

Before producing an answer, commit, PR, or artifact, resolve the seven-step runtime in `docs/INFERENCE_OPERATION_PROTOCOL.md`:

```text
1. resolve intent
2. load canonical context
3. compress semantic core
4. bind claims to evidence
5. select executable path
6. verify and falsify
7. emit replayable artifact
```

The required agent state is:

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

If this state cannot be resolved, return a blocked result. Do not invent context.

## Forbidden Behavior

Agents must not:

```text
- promote a hypothesis into measured status by wording alone
- remove a falsifier because it fails
- weaken schemas to make artifacts pass
- hide negative baseline or cost-model outcomes
- create decorative evidence files
- bypass claim-boundary checks by moving language into another document
- introduce dependency-heavy paths into the MFN gateway
- call a release complete without generated evidence
- rewrite the repository identity into a product promise
- skip the inference operation protocol when changing claim-facing surfaces
- treat an unclassified file as operational context
```

## Evidence-Bearing Artifact Minimum

A result can support promotion only if it records:

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

Minimum admissibility:

```text
score_source = computed
artifact_role != placeholder
falsification_status != NOT_RUN
baseline is explicit
replay_command is executable
schema validation passes
```

## Documentation Change Rule

For documentation-only changes:

```text
1. Keep wording consistent with PRODUCT_CATEGORY.md.
2. Keep claim tiers consistent with CLAIMS.md.
3. Avoid forbidden status language from FORBIDDEN_CLAIMS.md.
4. Link new conceptual docs from README.md or an existing canonical surface.
5. Do not create parallel doctrine files unless they reduce ambiguity.
6. Bind inference-facing documentation to docs/SEMANTIC_CONTROL_LAYER.md, docs/INFERENCE_READINESS.md, and docs/INFERENCE_OPERATION_PROTOCOL.md.
```

## Code Change Rule

For code changes:

```text
1. Identify the exact module and public contract.
2. Preserve deterministic behavior unless a test explicitly updates the contract.
3. Add or update tests for changed behavior.
4. Avoid network, clock, locale, or local-path dependence in core gates.
5. Keep MFN dependency-light unless the canonical gateway contract changes.
```

## Release Rule

A release-related change is incomplete until it emits or verifies:

```text
commands
raw logs
exit codes
manifest
checksums
schema validation result
CI status when available
replay path
```

A green command without persisted evidence is not a release proof. It is a nice little terminal mood swing.

## Preferred Final Response From Agents

When finishing work, report:

```text
Changed files:
Commit SHA:
Intent type:
Claim tier impact:
Verification command:
Evidence artifact path:
Blocked claims:
Remaining blocker:
```

Do not produce motivational summaries. The repository does not need therapy; it needs proof.
