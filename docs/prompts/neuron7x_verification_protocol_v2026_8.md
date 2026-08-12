# Neuron7X Verification Protocol v2026.8

## Purpose

This governance artifact defines how Neuron7X/FVPS outputs are verified against a declared specification.

Verification means proving conformance between:

```text
SPECIFICATION -> REQUIREMENT_SET -> EVIDENCE_LINKS -> CHECKS -> RESULT_STATE -> ALLOWED_ACTION
```

It does not claim runtime correctness, physics validation, predictive performance, trading readiness, or model-weight updates during inference.

## Verification Target

Every output or artifact must declare:

```text
object_id
specification_ref
requirement_set
evidence_set
verification_checks
observed_result
conformance_state
failure_boundary
rollback_path
```

## Conformance States

Use only:

```text
NON_CONFORMANT
UNVERIFIED
PARTIAL_CONFORMANCE
LOCALLY_CONFORMANT
CI_CONFORMANT
EVIDENCE_CONFORMANT
```

State mapping:

```text
NON_CONFORMANT        = contradiction against requirement or forbidden boundary
UNVERIFIED            = specification exists without executable evidence
PARTIAL_CONFORMANCE   = some requirements have evidence, but chain is incomplete
LOCALLY_CONFORMANT    = all required checks pass locally
CI_CONFORMANT         = local proof plus same-SHA CI proof
EVIDENCE_CONFORMANT   = CI proof plus real evidence, replay, baseline, falsifier, semantic validation
```

Never use vague states such as `mostly correct`, `green enough`, `looks aligned`, or `probably valid`.

## Verification Pipeline

```text
RAW_ARTIFACT
-> SPEC_LOAD
-> REQUIREMENT_EXTRACTION
-> EVIDENCE_BINDING
-> CHECK_EXECUTION
-> GAP_DETECTION
-> CONFORMANCE_QUANTIZATION
-> ACTION_DECISION
```

## Requirement Classes

```text
FORMAT_REQUIREMENT      structure, schema, required fields
MECHANISM_REQUIREMENT   cause -> process -> measurable result
EVIDENCE_REQUIREMENT    source, command, artifact, CI SHA
BOUNDARY_REQUIREMENT    explicit blocked claims
FAILURE_REQUIREMENT     break condition and negative evidence
ROLLBACK_REQUIREMENT    reversible path
```

## Verification Rules

1. A claim without source is `UNVERIFIED`.
2. A claim with source but no test is `PARTIAL_CONFORMANCE`.
3. A claim with local test proof but no same-SHA CI proof is `LOCALLY_CONFORMANT`.
4. A claim with same-SHA CI proof is `CI_CONFORMANT`.
5. A research claim requires real data, replay, baseline, falsifier, and semantic validation to become `EVIDENCE_CONFORMANT`.
6. Any contradiction with the specification is `NON_CONFORMANT`.
7. Any forbidden promotion is blocked even if formatting is valid.

## Score Function

```text
K = 0.18R + 0.16E + 0.16C + 0.14B + 0.14F + 0.12A + 0.10L
```

Where:

```text
R = requirement coverage
E = evidence binding
C = check execution
B = boundary compliance
F = failure-mode coverage
A = action correctness
L = rollback completeness
```

## Thresholds

```text
K < 0.35       NON_CONFORMANT
0.35 <= K < 0.55  UNVERIFIED
0.55 <= K < 0.72  PARTIAL_CONFORMANCE
0.72 <= K < 0.86  LOCALLY_CONFORMANT
0.86 <= K < 0.95  CI_CONFORMANT
K >= 0.95      EVIDENCE_CONFORMANT only if real evidence conditions are present
```

The score cannot promote a state above the weakest required proof link.

## Output Contract

```text
[VERIFICATION_TARGET]
<object and specification>

[REQUIREMENT_COVERAGE]
<covered / missing / contradicted>

[EVIDENCE_LINKS]
<source, test, command, artifact, CI SHA>

[CONFORMANCE_STATE]
<one allowed state>

[BLOCKED_PROMOTIONS]
<claims that cannot be raised>

[FAILURE_BOUNDARY]
<where conformance breaks>

[SYSTEM_ACTION]
<accept, patch, reject, quarantine, rollback>
```

## Boundary

This protocol verifies governance artifacts against their own specification. It does not verify scientific truth, trading edge, physical law, production safety, or market value unless those claims have independent executable evidence.
