# D-002C Null Audit Gap and C2.4-A2 Specification

## Problem

The null-audit aggregator (`research.systemic_risk.d002c_null_audit.run_null_audit_all`,
merged via PR #672 / C2.4-C2) exists and correctly emits a real
`d002c_null_audit_capsule_v1`. However, the sweep runner
(`research.systemic_risk.d002c_sweep_runner`) does NOT persist the per-seed
precursor and null paired sample values required by `run_null_audit_all`.

The sweep runner aggregates per-seed data into `signal_mean`, `bca_ci_lo/hi`,
`signal_over_ci`, and `direction`, then discards the per-seed pairs after
writing the cell payload to the D-002D checkpoint.

## Current consequence

The canonical D-002C run (RUN_ID `d002c_canonical_20260512T122837Z`)
passed R1 ∧ R2 ∧ R3 and emitted
`tier=SYNTHETIC_GATE6_CERTIFIED_REDESIGN_N_LE_200`, but the null-audit
permutation-test safeguard described in the pre-registration was NOT
fully exercised. Post-sweep `run_null_audit_all(sweep_capsule_path=ckpt)`
returned `NullAuditAggregateInvalid: resolved cell list is empty`.

## Required data contract

Each evaluated cell must persist into the checkpoint and/or output
capsule a `NullAuditCellPayload` frozen dataclass with these fields:

```python
@dataclass(frozen=True)
class NullAuditCellPayload:
    cell_key: str                       # canonical "[N,λ,sub,metric]"
    N: int
    lambda_: float
    substrate_id: str
    metric_id: str
    seed_ids: tuple[int, ...]            # n_seeds entries
    precursor_values: tuple[float, ...]  # same length as seed_ids
    null_values: tuple[float, ...]       # same length as seed_ids
    paired_by_seed: bool                 # MUST be True under paired CRN
    crn_identity_hash: str               # binds the CRN pairing identity
    metric_version: str
    substrate_version: str
    generated_at: str
    sha256: str                          # canonical_preflight_json sha
```

The `precursor_values` and `null_values` arrays are the per-seed metric
values BEFORE aggregation. They are the load-bearing input to
`run_null_audit_all` — without them, the aggregator has no permutation
test material.

The `paired_by_seed=True` flag is asserted so the aggregator can refuse
to audit a payload that was not produced under the paired CRN protocol.

## Acceptance criteria

C2.4-A2 passes only if ALL of the following hold:

1. `sweep_runner.run_one_cell` emits a `NullAuditCellPayload` for every
   evaluated cell (not just SKIPPED_BY_PREFLIGHT).
2. The D-002D checkpoint preserves the payload across resume — a
   killed-and-restarted sweep produces byte-identical audit payload
   for the same cell.
3. `run_null_audit_all(sweep_capsule_path=...)` consumes those payloads
   and emits a `d002c_null_audit_capsule_v1` with a non-empty `results`
   list.
4. `aggregate_only` is NOT set on the post-sweep null_audit capsule
   (the escape hatch is reserved for the legitimate pre-sweep empty
   state, never for "we don't have data" silent passes).
5. An injected null FAIL on a single cell flips the aggregate verdict
   to FAIL.
6. A corrupted payload sha (one byte tampered) makes the post-sweep
   audit refuse the cell.
7. A resumed sweep produces an identical payload sha to the original
   uninterrupted sweep.
8. No claim layer is modified by C2.4-A2.
9. `docs/governance/D002C_PREREGISTRATION.yaml` is NOT modified.
10. `research/systemic_risk/d002c_preflight.py` validator is NOT
    modified (the validator is correct).

## Forbidden in C2.4-A2

- ❌ Threshold tuning of R1/R2/R3
- ❌ Modification of the pre-registration YAML
- ❌ Fake per-seed reconstruction from `signal_mean` ± bootstrap CI
  (the aggregator must receive the actual per-seed values; reconstruction
  loses the load-bearing CRN pairing identity)
- ❌ `aggregate_only` fallback for non-empty grids (silent pass via
  empty results is a contract violation)
- ❌ Claim promotion (this PR is correctness-only infrastructure)
- ❌ Modification of `d002c_substrates.py`, `d002c_metrics.py`,
  `d002c_kuramoto.py` (the science layer)

## Post-merge action

After C2.4-A2 merges to main:

1. Fresh `RUN_ID` (`d002c_canonical_attempt_2_<timestamp>`).
2. Regenerate POS / NEG / SMOKE preflight capsules (new run identity).
3. Pre-sweep `null_audit.json` remains `aggregate_only=true` (legitimately
   empty — the pre-sweep state hasn't changed).
4. Run canonical sweep — now emitting per-cell `NullAuditCellPayload`.
5. Post-sweep `run_null_audit_all(sweep_capsule_path=ckpt)` consumes
   the real payloads.
6. If `aggregate_verdict=FAIL` on any audited cell, the verdict deriver
   is re-invoked with `--null-audit-failed`, flipping the tier to FAIL.
7. New evidence archive + claim ledger entry.

## Test plan (for C2.4-A2 PR)

Required new tests:

```
tests/research/systemic_risk/test_d002c_sweep_runner_null_audit_payload.py
  test_payload_emitted_for_every_computed_cell
  test_precursor_and_null_arrays_same_length_as_seed_ids
  test_paired_by_seed_is_true
  test_payload_sha_deterministic_across_calls
  test_checkpoint_resume_preserves_payload_byte_identically
  test_no_payload_for_SKIPPED_BY_PREFLIGHT_cells

tests/research/systemic_risk/test_d002c_null_audit_aggregator_integration.py
  test_aggregator_consumes_sweep_runner_payloads_and_emits_real_results
  test_aggregate_only_is_false_in_normal_post_sweep_path
  test_injected_FAIL_flips_aggregate
  test_preflight_refuses_capsule_with_FAIL_cell
  test_corrupted_payload_sha_refused
  test_old_checkpoint_schema_migration_is_versioned_or_refused
```

Plus regression on:

```
test_d002c_sweep_runner.py (no contract relaxation)
test_d002c_sweep_runner_preflight_integration.py (no breakage)
test_d002c_null_audit_aggregator.py (no contract relaxation)
test_d002c_preflight.py (no breakage)
test_false_confidence_detector.py (no new findings)
```

## Claim boundary on C2.4-A2

This will be an **infrastructure correctness** PR. It DOES NOT make any
scientific claim. It removes a structural gap that prevents the
pre-registered null-audit safeguard from executing on real sweep data.
