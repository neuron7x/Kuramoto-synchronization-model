# GeoSync Epistemic Rhombus manifest validation framework

> Status: governance policy index  
> Owner: platform-governance@geosync  
> Effective date: 2026-06-04  
> Validation: schema-backed JSONL validation via `scripts/validate_epistemic_rhombus_manifest.py`

## Purpose

The Epistemic Rhombus is a repository-level acceptance index for mapping
engineering assets to GeoSync governance expectations. It is not a cryptographic
ledger and does not claim tamper resistance. Repository history plus accepted
signed identity artifacts are the provenance boundary; this manifest records the
policy criteria and external gates that must supply the actual evidence.

## Non-goals

The manifest does not prove the scientific truth of a domain claim, does not
verify signatures directly, does not replace Git object integrity, and does not
execute the referenced gates. It validates the governance contract that binds
criteria to fail-closed external enforcement points. Actual domain evidence stays
owned by the referenced workflows and audit artifacts.

## Rhombus criteria

| Axis | Criterion | Deployment blocker |
|------|-----------|--------------------|
| Axiomatic Basis | Every operational claim derives from a pre-registered data contract or defined physical/logical invariant. | Claim is discarded when no contract or invariant is named. |
| Structural Integrity | Every module/function has a falsification-ledger entry, mapped unit/property test, and fail-closed condition. | Module is not deployment-ready without test mapping and execution evidence. |
| Operational Determinism | Execution state is immutable where possible; side effects are isolated behind declared control gates. | State transition is rejected when replay cannot reproduce it in a compliant environment. |
| Provenance Governance | Significant claims, evidence, and deployment metadata are attributable to repository history and signed identity artifacts. | Deployment is blocked when attributable identity evidence is missing. |

## Required manifest fields

Each JSONL record in `governance/epistemic_rhombus_manifest.jsonl` must satisfy
`schemas/governance/epistemic_rhombus_manifest.schema.json` and contain:

- `record_id`: stable unique identifier for the criterion record. Canonical
  binding is axis-order based: `axiomatic_basis → ER-1`,
  `structural_integrity → ER-2`, `operational_determinism → ER-3`, and
  `provenance_governance → ER-4`.
- `axis`: one of the four Rhombus criteria defined by the schema enum; each
  schema-declared axis must appear exactly once.
- `criterion`: the acceptance statement.
- `invariant_or_contract`: the named invariant, data contract, or logic contract.
- `validation_gate`: the acceptance or rejection rule expressed for operators.
- `fail_closed_condition`: the condition that blocks deployment.
- `evidence_required`: non-empty artifact classes required before promotion.
- `control_gates`: non-empty side-effect gates covered by the criterion, using
  the schema-defined `G<n>` pattern. Gate identifiers must be globally unique
  across records.
- `enforcement`: the external workflow or command that owns executable gate logic;
  `blocks_on_failure` must be `true`.
- `provenance`: required signed identity boundary for the record's evidence.
- `threat_model`: non-empty `failure_modes`, non-empty `negative_controls`, and
  an explicit `residual_risk` value.

## External gate requirements

For `enforcement.mode = "external_gate"`, the first command token must point to a
repository workflow under `.github/workflows/*.yml` or `.github/workflows/*.yaml`.
The validator rejects missing workflow files, `pull_request_target`, and workflows
that do not declare `permissions: contents: read`. A workflow must expose a
`pull_request` or `merge_group` trigger so the gate is connected to the review or
merge path rather than existing as ceremonial YAML.

## Threat model

| Failure class | Validator control |
|---------------|-------------------|
| Decorated metadata with no blocker | `blocks_on_failure` is schema-constant `true`. |
| Axis drift | Every schema-declared axis must appear exactly once. |
| Identity drift | `record_id` is unique and canonically bound to axis order. |
| Gate collision | `control_gates` are non-empty and globally unique. |
| Unsafe CI boundary | `pull_request_target` is rejected for external gates. |
| Excessive workflow permission | External gate workflows must declare read-only contents permission. |
| Evidence ambiguity | Each record declares required evidence, fail-closed condition, provenance, and threat model. |

## Validation command

```bash
python scripts/validate_epistemic_rhombus_manifest.py \
  --report reports/governance/epistemic_rhombus_manifest.validation.json
```

The validator streams JSONL records, applies the JSON schema directly, checks
that every schema-declared axis appears exactly once, rejects duplicate
`record_id` values, rejects empty or duplicate gate coverage, validates external
gate workflow safety properties, and emits a deterministic JSON report when
`--report` is supplied. It does not validate signatures; signature verification
remains the responsibility of the referenced external gates.

## CI gate

`.github/workflows/epistemic-rhombus-gate.yml` runs the live manifest validation
and `tests/scripts/test_validate_epistemic_rhombus_manifest.py` on Python 3.11
and 3.12 whenever the manifest, schema, validator, documentation, claim ledger,
or the gate itself changes. The workflow also runs on merge queue, writes
`reports/governance/epistemic_rhombus_manifest.validation.json`, and uploads that
file as a build artifact. This keeps the Rhombus from drifting into non-executable
governance metadata.
