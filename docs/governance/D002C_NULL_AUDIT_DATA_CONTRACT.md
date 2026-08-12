# D-002C Null-Audit Data Contract

**Closes:** `docs/governance/D002C_NULL_AUDIT_GAP_AND_C2_4_A2_SPEC.md`

## Purpose

After C2.4-A2 lands, the D-002C sweep runner persists per-seed
precursor/null paired metric values for every computed cell. The
existing `run_null_audit_all` aggregator (C2.4-C2) can then audit
those payloads, emit a real `d002c_null_audit_capsule_v1`, and
the preflight validator (C2.4-D) consumes it. The
`aggregate_only=true` escape hatch is reserved for the legitimate
pre-sweep empty-grid state and is NOT used in the post-sweep path.

## Data contract — `NullAuditCellPayload`

```python
@dataclass(frozen=True)
class NullAuditCellPayload:
    cell_key: str                       # canonical "[N,λ,sub,metric]"
    N: int
    lambda_: float
    substrate_id: str
    metric_id: str
    seed_ids: tuple[int, ...]            # length n_seeds
    precursor_values: tuple[float, ...]  # SAME length as seed_ids
    null_values: tuple[float, ...]       # SAME length as seed_ids
    paired_by_seed: bool                 # MUST be True under paired CRN
    crn_identity_hash: str               # binds the CRN pairing identity
    metric_version: str
    substrate_version: str
    generated_at: str
    sha256: str                          # canonical_preflight_json sha
```

## Paired-array invariants

For every emitted `NullAuditCellPayload`:

- `len(seed_ids) == len(precursor_values) == len(null_values)`
- `paired_by_seed is True` (under the paired-CRN protocol locked in C2.3)
- every element of `precursor_values` / `null_values` is finite

A payload with `paired_by_seed=False` is REFUSED by
`NullAuditCellPayload.from_payload_dict` — the aggregator MUST not
audit unpaired data.

## SHA computation

The payload's `sha256` is computed using
`research.systemic_risk.d002c_preflight.canonical_preflight_json`,
the SAME canonical formula that the preflight validator uses to
recompute the capsule sha. This guarantees round-trip alignment
end-to-end:

  writer (sweep_runner) → checkpoint → reader (run_null_audit_all)
  → emitted null_audit.json → preflight validator recompute = PASS

The sha excludes the `sha256` field itself AND the `generated_at`
field (so a machine-clock difference between calls does not change
the sha — pure-content addressing).

## Checkpoint / resume contract

- The D-002D `CheckpointManager` persists each per-cell payload as
  a JSON sub-dict on the cell result.
- Resume of an interrupted sweep MUST produce byte-identical
  payload sha256 for already-completed cells.
- Schema versioning: the payload carries `metric_version` and
  `substrate_version` tags; if the on-disk format changes
  incompatibly, the schema_version is bumped and old files are
  either migrated forward or refused fail-closed.

## Skipped-cell handling

`SKIPPED_BY_PREFLIGHT` cells (excluded by POS/NEG preflight gates)
do NOT receive a `NullAuditCellPayload` — the absence of metric
evidence is recorded as `status=SKIPPED_BY_PREFLIGHT` in the
checkpoint and the aggregator's `SKIPPED_NO_PER_SEED_DATA`
sentinel is reserved for cells that failed to emit a payload
through any OTHER path.

The aggregator MUST treat any non-SKIPPED_BY_PREFLIGHT cell that
lacks a payload as a hard fail (`aggregate_verdict=FAIL`), not as
an implicit pass — absence of audit evidence is never evidence of
audit success.

## Aggregator behavior under this contract

`run_null_audit_all(sweep_capsule_path=ckpt)`:

1. Reads the checkpoint, extracts every cell's `NullAuditCellPayload`.
2. For each payload, runs the paired-difference permutation test
   on `(precursor_values, null_values)` (the C2.4-C2 contract).
3. Per-cell verdict: PASS iff the empirical p-value (fraction of
   shuffles with `|shuffled| >= |unshuffled|`) is BELOW the
   pre-registered threshold.
4. Aggregate verdict: PASS iff every audited cell is PASS AND
   there are no SKIPPED_NO_PER_SEED_DATA cells.
5. Emits `d002c_null_audit_capsule_v1` with non-empty `results`,
   `aggregate_only=false`, and sha computed via
   `canonical_preflight_json`.

## Preflight integration

After the sweep:

1. The operator (or a wrapper script) invokes `run_null_audit_all`
   on the sweep checkpoint.
2. The emitted `null_audit.json` REPLACES the pre-sweep
   `aggregate_only=true` capsule in the preflight directory.
3. Re-validation via `load_and_validate_preflight_capsules` MUST
   produce `launch_allowed=True` if all cells PASS, `False` with
   `null_not_pass` refusal_reasons if any cell FAILed.
4. If `launch_allowed=False`, the verdict deriver is re-invoked
   with `--null-audit-failed` to flip the tier to FAIL.

## Required tests

`tests/research/systemic_risk/test_d002c_sweep_runner_null_audit_payload.py`:

- Payload emission per computed cell
- Paired-array length invariants
- `paired_by_seed=True` invariant
- sha deterministic across calls
- Checkpoint resume preserves payload byte-identically
- No payload for `SKIPPED_BY_PREFLIGHT` cells
- Corrupted payload sha refused
- Old schema versioned or refused
- Paired-array length mismatch refused
- Finite values for non-trivial signal

`tests/research/systemic_risk/test_d002c_null_audit_aggregator_integration.py`:

- `run_null_audit_all` consumes real sweep payloads
- Aggregate PASS / FAIL well-defined under real data
- Injected strong-signal FAIL flips aggregate verdict
- Preflight refuses when null_audit contains a FAIL cell
- `aggregate_only=False` in normal post-sweep path
- No claim-layer artifact modified (regression on YAML schema)
- Empty results without aggregate_only refused
- Aggregator sha matches preflight canonical recompute

## CI requirements

```
ruff check    research/systemic_risk/d002c_sweep_runner.py
              research/systemic_risk/sweep_checkpoint.py
              research/systemic_risk/d002c_null_audit.py
              tests/research/systemic_risk/test_d002c_sweep_runner_null_audit_payload.py
              tests/research/systemic_risk/test_d002c_null_audit_aggregator_integration.py
black --check (same)
mypy --strict --follow-imports=silent (same)
pytest -q (all D-002C test files + false_confidence_detector)
```

## Rollback command

```bash
git revert <merge-commit-sha-of-this-PR>
```

The new `NullAuditCellPayload` dataclass and the per-cell payload
fields are additive on the checkpoint schema; old checkpoints
without the payload load cleanly and surface as
`SKIPPED_NO_PER_SEED_DATA` to the aggregator (fail-closed).

## Claim boundary

C2.4-A2 is an **infrastructure correctness** PR. It does NOT:

- ❌ make any new scientific claim
- ❌ promote any tier
- ❌ modify acceptance thresholds (R1/R2/R3)
- ❌ modify the locked `D002C_PREREGISTRATION.yaml`
- ❌ modify the verdict deriver or its tier strings
- ❌ modify substrate or metric math

It DOES:

- ✅ close the executable null-audit data contract gap documented
  in `D002C_NULL_AUDIT_GAP_AND_C2_4_A2_SPEC.md`
- ✅ enable the post-canonical-rerun audit safeguard to operate on
  real sweep output
- ✅ preserve the canonical D-002C PASS already frozen in
  `D002C_CANONICAL_RUN_REPORT.md` (no regression)

The next step after C2.4-A2 merges is a **post-C2.4-A2 canonical
rerun** with executable null audit. That rerun, not this PR, is
the path to upgrading the claim ledger entry beyond
`SUPPORTED_SYNTHETIC_SCOPED`.
