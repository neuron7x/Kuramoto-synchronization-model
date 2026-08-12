# BBB-NVU Cognitive Noise Gate Product Readiness Manifest

## Status

Engineering status: bounded operational prototype.

Clinical status: research-use only. The artifact does not diagnose, treat, prescribe, triage, or authorize real-world care decisions.

## Product boundary

This subsystem is ready to be consumed as a deterministic repository artifact when all listed gates are green:

1. `Commit Acceptor Gate`
2. `PR Gate / python-quality`
3. `PR Gate / secrets-supply-chain`
4. `Readiness Gate`
5. `Physics Invariants`
6. `Architectural Connectome Gate`
7. `python BBB_NVU_Cognitive_Noise_Gate_2026/tools/verify_artifact.py`

The release unit is the directory `BBB_NVU_Cognitive_Noise_Gate_2026/` plus its diff-bound acceptors.

## Canonical value function

The artifact value function is:

```text
Value = verified closure under deterministic replay.
```

A change has value only when it produces a bounded artifact that can be rerun, replayed, audited, and rejected when its contracts are violated. A markdown claim without an executable or hash-bound verification path is not promoted to product evidence.

## Operational inference chain

The canonical inference chain is:

```text
RuntimeRequest
  -> L1 schema and numeric gate
  -> deterministic risk engine
  -> bounded risk state
  -> control-action envelope
  -> audit event
  -> replay bundle
  -> metrics snapshot
  -> incident register
  -> verification artifact
  -> CI release gate
```

This chain is deliberately narrow. It favors a small deterministic surface over a large speculative system because product reliability comes from closed loops, not from vocabulary inflation, humanity's favorite substitute for shipping.

## Runtime contract

The stable integration surface is:

- `RuntimeBoundary.evaluate_run(...)`
- `RuntimeBoundary.evaluate_batch(...)`
- `OperationalKernel.execute(...)`
- `verify_operational_envelope(...)`

The CLI is a compatibility adapter. Product consumers should not couple to CLI parsing.

## Evidence contract

The canonical verifier writes:

```text
tmp/bbb_nvu_cng_verify_artifact.json
```

The artifact records Python version, command status, JSON parsing, Python compilation, focused pytest, operational smoke result, hash material, and whitespace integrity.

## Determinism contract

The deterministic identity of one run is bound by:

```text
input_hash + rules_hash + engine_hash -> run_hash
```

An operational envelope is accepted only when output hashes, audit hashes, replay bundle hashes, replay verification, metrics snapshot id, incident ids, and request cardinality are internally consistent.

## Fail-closed contract

Invalid schema, non-finite numeric values, out-of-range domain values, or explicitly invalid input must produce a bounded invalid output path with zero confidence. Missing or degraded data must be visible as degradations, not silently interpreted as clean evidence.

## State interpretation

| State | Operational meaning | Allowed integration behavior |
| --- | --- | --- |
| `GREEN_STABLE` | Input passed L1 contracts and deterministic rules did not identify a watch/risk/invalid condition. | Record, expose metrics, no escalation requirement. |
| `YELLOW_WATCH` | Evidence is degraded, low-confidence, or near a watch boundary. | Keep visible, collect more data, do not silently mark clean. |
| `ORANGE_RISK` | Multiple risk signals or stronger rule activation. | Require human review before dependent action. |
| `RED_CRITICAL` | Critical deterministic rule activation. | Block autonomous execution and open urgent review. |
| `BLACK_INVALID` | Input contract failed or data integrity is explicitly invalid. | Zero confidence, block dependent execution, preserve audit trail. |

## Promotion algebra

A PR-level promotion is valid only when:

```text
PROMOTE =
  commit_acceptor_gate
  and repo_policy_gate
  and secrets_supply_chain_gate
  and python_quality_gate
  and readiness_gate
  and physics_invariants_gate
  and architectural_connectome_gate
  and focused_verifier_passes
```

If any operand is false, the artifact remains a bounded prototype, not a promoted subsystem. This is intentionally harsh because soft gates create hard incidents later, a tiny tragedy apparently requiring endless rediscovery.

## Operational runbook

1. Execute `python BBB_NVU_Cognitive_Noise_Gate_2026/tools/verify_artifact.py`.
2. Confirm `tmp/bbb_nvu_cng_verify_artifact.json` has `status=passed`.
3. Confirm replay bundles verify under `verify_operational_envelope(...)`.
4. Confirm no `BLACK_INVALID` output is treated as actionable evidence.
5. Confirm incidents are generated for non-green states and preserve review constraints.
6. Confirm CI gates are green before merge.
7. Promote only the directory plus its acceptors as the release unit.

## Canonical interpretation of this PR

This PR converts the BBB-NVU concept from a narrative research seed into a deterministic operational prototype. Its strongest product property is not biological authority. Its strongest property is that every accepted run has a replayable identity, a bounded state, a visible degradation path, and an audit/incident envelope.

The correct reading is:

```text
This is a reproducible inference-control artifact, not a clinical claim engine.
```

## Non-goals

This PR does not claim:

- biological validation;
- prospective human validation;
- medical-device readiness;
- autonomous decision authority;
- production service hosting;
- real sensor ingestion;
- privacy or consent completeness for live deployment.

## Next promotion gate

Promotion from bounded operational prototype to integration-ready subsystem requires a follow-up PR that moves the package into a canonical import namespace, adds a release manifest with file digests, and binds artifact verification into CI as a named required check.

## Next expansion vector

The next expansion must be narrow and test-bound:

1. package namespace: `geosync.cns.bbb_nvu_cng`;
2. machine-readable release manifest with file digests;
3. CI-required focused verifier check;
4. mutation tests for envelope verification failure cases;
5. typed public API examples for integrators;
6. no expansion of clinical claims without external validation evidence.
