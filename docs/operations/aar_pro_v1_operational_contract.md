# AAR-PRO-V1 Operational Contract

## Problem statement

Every action-result update must be accepted only when a sealed pre-action model,
a post-action observation, and a deterministic witness form one replayable,
tamper-evident chronology.

## Falsifiable hypothesis

If any outcome is missing a sealed expected model, violates
`model_created_seq < action_started_seq < observed_seq`, changes the observed
payload after evidence sealing, or accumulates unsafe DRO-ARA comparator energy,
then the system must refuse normal sanctioning and emit rollback / reduction
semantics.

## Machine-readable invariant registry

Canonical operational data for this contract is stored in
`docs/operations/aar_pro_v1_invariants.yaml`. That registry binds the
problem statement, falsifiable hypothesis, formulas, invariant IDs, enforcement
code paths, test references, smoke/readiness commands, evidence artifacts, and
kill-switch predicates in one parseable artifact. The markdown document is the
human interpretation layer; the YAML file is the reviewable product contract.

## Runtime contract

| Layer | Contract | Failure mode |
|---|---|---|
| Comparator | `accept_action_result(expected, observed)` is pure and deterministic. | `INVALID_INPUT`, `ACTION_MISMATCH`, or `ROLLBACK_REQUIRED`. |
| Evidence | `seal_action_result_evidence()` binds expected, observed, and witness digests. | `EVIDENCE_WITNESS_MISMATCH` for stale/forged witnesses. |
| Episode | `ControlEpisode` advances by monotonic sequence and hash-chain records. | Out-of-order afferentation is bound as rejected evidence and closes the episode. |
| AAR tracker | `AARTracker.record_outcome()` requires a prior prediction. | Raises; no default prediction synthesis. |
| DRO-ARA | Comparator error feeds a Gaussian variational-energy proxy and adaptive belief state. | Dynamic threshold breach forces `INVALID`/`REDUCE`/`risk_scalar=0` and emits `REDUCE_RISK`. |
| Self-healing | `prescribe_recovery()` maps witnesses to bounded recovery actions. | Blocks weight updates, rolls back, reseals, quarantines, or reduces risk. |
| Chronology | DRO-ARA event ordering uses a monotone SHA-256 event chain. | Synthetic `3*step_index` chronology is forbidden by falsification tests. |
| Formal model | `formal/AAR_PRO_V1.tla` records chronology/fail-closed invariants. | Static invariant binding test fails if the spec loses required invariants. |

## State diagram

```text
INTENT_DECLARED
  -> MODEL_SEALED
  -> ACTION_DISPATCHED
  -> AFFERENTATION_RECEIVED
  -> ERROR_COMPUTED
  -> DECISION_RENDERED
  -> MEMORY_ANCHORED
```

Rejected asynchronous afferentation follows the same hash-chain discipline but
short-circuits after `ERROR_COMPUTED` with a rollback-required invalid witness.

## One-command smoke

```bash
python scripts/aar_pro_smoke.py
python scripts/aar_pro_readiness.py
```

Expected deterministic shape:

```json
{"accepted":true,"chain_verified":true,"episode_closed":true,"last_phase":"MEMORY_ANCHORED","model_update_allowed":true,"phase_count":7,"recovery_action":"ALLOW_MODEL_UPDATE","rollback_required":false,"schema_version":"AAR-PRO-V1-SMOKE","status":"SANCTIONED_MATCH"}
```

The emitted `evidence_digest` is intentionally omitted above because it is a
64-character SHA-256 digest tied to the exact canonical payloads.

The readiness command is a stricter product gate: it compiles the core runtime modules, rejects source-level truncation/synthetic chronology regressions, verifies the precision-distance formula numerically, and checks the DRO-ARA observer circuit-breaker output contract.

Scoped governance validation should use `--acceptor-id canonical-action-result-comparator --acceptor-id aar-pro-verification-suite --acceptor-id aar-pro-operational-governance` so the partitioned AAR-PRO gate fails on its own schema/evidence/diff binding while suppressing unrelated historical acceptor evidence warnings and respecting per-claim file-count caps.

## Kill-switch / rollback path

- Runtime kill-switch: treat any `rollback_required=True`,
  `free_energy_circuit_breaker=True`, `chain_verified=False`, or any recovery plan without `ALLOW_MODEL_UPDATE` as a hard stop
  for downstream model-weight updates.
- Code rollback: use the `rollback_command` and
  `rollback_verification_command` recorded in
  `.claude/commit_acceptors/canonical-action-result-comparator.yaml`.

## Ownership

Artifact owner: `geosync_hpc/control` maintainers. Governance ledger:
`.claude/commit_acceptors/canonical-action-result-comparator.yaml`.
