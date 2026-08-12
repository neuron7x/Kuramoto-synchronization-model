# Claim-State Quantum Input Contract

## Purpose

Claim-State Quantum is a governance data contract. It converts one raw evidence envelope into exactly one discrete state:

```text
FALSE
UNTESTED
PARTIAL
LOCAL_VERIFIED
CI_VERIFIED
EVIDENCE_BEARING
```

It exists to remove ambiguous release language such as `almost ready`, `green enough`, or `looks correct`.

## Input envelope

Required fields:

| Field | Meaning |
| --- | --- |
| `claim_id` | Stable identifier for the claim. |
| `claim_text` | Human-readable claim. |
| `source_refs` | Source files or references supporting the claim. |
| `test_refs` | Tests binding the claim. |
| `commands` | Commands used to reproduce the evidence. |
| `artifacts` | Output artifacts created by the commands. |
| `ci_proof` | Same-SHA CI result metadata. |
| `failure_mode` | What failure the contract is meant to catch. |
| `rollback` | Reversible path if the change is wrong. |
| `claim_boundary` | Allowed and blocked interpretations. |
| `negative_evidence` | Known gaps or failed proof links. |

## Quantization law

```text
raw evidence -> normalized proof vector -> hard threshold gate -> discrete claim state -> allowed action
```

## Promotion rules

- `FALSE`: claim is contradicted.
- `UNTESTED`: no proof-chain links exist.
- `PARTIAL`: some proof exists, but at least one required link is missing.
- `LOCAL_VERIFIED`: required local proof-chain links exist.
- `CI_VERIFIED`: local proof plus same-SHA required CI success.
- `EVIDENCE_BEARING`: real data, replay, baseline, falsifier, and semantic validation exist.

Never round upward. If declared state is higher than computed state, the CLI exits non-zero.

## CLI

```bash
python tools/governance/quantize_claim_state.py --input claim-evidence.json
```

## Boundary

This is governance infrastructure. It does not validate physics, markets, cognition, trading performance, or predictive power.
