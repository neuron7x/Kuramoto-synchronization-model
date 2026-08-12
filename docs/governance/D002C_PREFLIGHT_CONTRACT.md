# D-002C C2.4-D — Preflight Enforcement Contract

Status: preflight-enforced, synthetic-only, fail-closed, deterministic
under fixed inputs, claim-neutral.

This document defines the **launch-gating layer** that binds the
D-002C C2.4 sibling sessions A/B/C to the sweep runner. The contract
is enforced at runtime by
`research.systemic_risk.d002c_preflight` and consumed by
`research.systemic_risk.d002c_sweep_runner.run_sweep`.

## Purpose

A 69,120-cell falsification sweep must not launch on a stale, missing,
or tampered preflight verdict. Before C2.4-D, the runner only checked
the sweep config against the pre-registration; the four preflight
capsules (`pos_control`, `neg_control`, `null_audit`, `smoke_test`)
were emitted by sessions A/B/C but **never consulted at launch time**.
C2.4-D closes that gap.

The preflight enforcement layer:

1. loads, parses, and validates the four capsules,
2. recomputes the canonical-JSON sha256 of each capsule body sans the
   `sha256` field and refuses on mismatch,
3. checks substrate / metric / N identities against the runtime
   registries (`ALL_SUBSTRATES`, `ALL_METRICS`,
   `DEFAULT_NEG_N_GRID`),
4. interprets each capsule's verdict per the rules in this document,
5. emits a frozen `PreflightDecision` whose own sha256 is folded into
   the aggregate sweep sha — so capsule tampering between runs changes
   the sweep sha by construction.

## Non-goals

- The preflight emits **no claim** of its own.
- The preflight does **not** mutate the pre-registration.
- The preflight does **not** retune any scientific threshold.
- The preflight does **not** tolerate warnings as acceptable for
  launch-critical state.
- The preflight does **not** silently skip a missing or malformed
  capsule.

## Capsule schemas

### `pos_control` — `kind: d002c_pos_control_capsule_v1`

Emitted by `d002c_pos_control.run_pos_control_all`. Required fields
consulted by the preflight:

- `kind == "d002c_pos_control_capsule_v1"`
- `sha256` (canonical-JSON sha256 over the body sans `sha256`)
- `generated_at` (ISO-like timestamp)
- `excluded_combos: list[[substrate_id, metric_id]]`
- `results: list[{substrate_id, metric_id, signal_ci_ratio, threshold,
   censoring_fraction, …}]`

Refusal: bad/missing kind, sha mismatch, missing timestamp, unknown
substrate / metric id in any combo or result, non-finite numeric in a
load-bearing field.

### `neg_control` — `kind: d002c_neg_control_capsule_v1`

Emitted by `d002c_neg_control.run_neg_control_all`. Required fields:

- `kind == "d002c_neg_control_capsule_v1"`
- `sha256`, `generated_at`
- `excluded_cells: list[[substrate_id, metric_id, N]]`
- `results: list[{substrate_id, metric_id, N, fpr, alpha_bonferroni,
   threshold_tolerance, …}]`

Refusal: bad kind, sha mismatch, missing timestamp, unknown
substrate / metric / N in any cell or result, non-finite numeric.

### `null_audit` — `kind: d002c_null_audit_capsule_v1`

Emitted by an orchestrator that wraps per-cell
`d002c_null_audit.NullAuditResult` payloads. Required fields:

- `kind == "d002c_null_audit_capsule_v1"`
- `sha256`, `generated_at`
- `results: list[{verdict: "PASS" | "FAIL", p_value_empirical, …}]`
  (each entry is a `NullAuditResult` payload)
- Optional `aggregate_only: bool` — set `True` if the capsule
  legitimately carries no auditable cells (C2.3-style aggregate-only
  output). When absent, an empty `results` list refuses launch.

Refusal: any cell's `verdict != "PASS"`, empty `results` (unless
`aggregate_only=True`), bad kind, sha mismatch, non-finite p-value.

### `smoke_test` — structural kind `d002c_smoke_test_capsule_v1`

Emitted by `d002c_smoke_test.run_smoke_test`. The writer module emits
**no `kind` field**; the preflight identifies the capsule
structurally by the presence of the canonical field set
(`verdict`, `grid_N`, `grid_lambda`, `n_cells_total`, `n_cells_ok`,
`n_cells_failed`, `cells`, `sha256`, `generated_at`).

Required:

- `verdict == "PASS"`
- `n_cells_failed == 0`

Refusal: missing structural fields, sha mismatch, `verdict != "PASS"`,
any non-zero `n_cells_failed`.

## Launch refusal matrix

| Condition                                                                 | launch_allowed |
| ------------------------------------------------------------------------- | -------------- |
| Any of the four capsule files is missing                                  | False          |
| Any capsule is non-JSON or its root is not a JSON object                  | False          |
| Any capsule's declared `kind` does not match the expected marker          | False          |
| Any capsule's recomputed canonical-JSON sha256 disagrees with `sha256`    | False          |
| Any capsule lacks a `generated_at` timestamp                              | False          |
| Smoke capsule `verdict != "PASS"` OR `n_cells_failed > 0`                 | False          |
| Null-audit `results` is empty (and `aggregate_only` not set)              | False          |
| Any null-audit cell `verdict != "PASS"`                                   | False          |
| Any capsule references an unknown substrate / metric id, or unknown N    | False          |
| Any load-bearing numeric field is non-finite (NaN / Inf)                  | False          |
| POS `excluded_combos` is non-empty                                        | **True**       |
| NEG `excluded_cells` is non-empty                                         | **True**       |

POS / NEG exclusions are by design **grid reducers**, not launch
blockers — the preflight contract is "if these gates ran and the gate
emitted exclusions, run the rest, not nothing".

## Grid exclusion semantics

- **POS** `excluded_combos: list[(substrate_id, metric_id)]` —
  every sweep cell whose `(substrate_id, metric_id)` matches is
  removed from the runnable grid. This affects **all** `(N, λ)`
  combinations of the matched cell.
- **NEG** `excluded_cells: list[(substrate_id, metric_id, N)]` —
  every sweep cell whose `(substrate_id, metric_id, N)` triple
  matches is removed. Siblings at different `N` survive.

Skipped cells are emitted as `SkippedCell` records carrying
`source_capsule`, `source_capsule_sha256`, and `reason`
(`POS_EXCLUDED_COMBO` or `NEG_EXCLUDED_CELL`).

## Checkpoint skipped-cell semantics

The `CheckpointManager` ledger gains a `SKIPPED_BY_PREFLIGHT`
`CellResult` variant. The payload schema is:

```json
{
  "cell_key": "[N,lambda,substrate_id,metric_id]",
  "substrate_id": "...",
  "metric_id": "...",
  "N": ...,
  "lambda_": ...,
  "status": "SKIPPED_BY_PREFLIGHT",
  "reason": "POS_EXCLUDED_COMBO|NEG_EXCLUDED_CELL",
  "source_capsule": "pos_control|neg_control",
  "source_capsule_sha256": "..."
}
```

A SKIPPED entry has `duration_seconds == 0.0`. The
`IDEMPOTENT_ONLY` overwrite policy ensures a resume cannot
silently turn a SKIPPED cell into a computed one — the second pass
would attempt to save an identical SKIPPED payload (idempotent
no-op).

The aggregate sweep sha is computed over:

- `preregistration_sha`
- per-computed-cell sha list (sorted)
- `completed_cells`, `total_cells`, `rng_seed_base`,
  `steps_per_quarter`, `omega_gamma`
- `preflight_decision_sha` — the preflight's content-addressed sha
- `skipped_cell_keys` (sorted)
- `skipped_cell_source_shas`

Capsule tampering between runs changes the preflight decision sha,
which changes the sweep sha.

## Deterministic hashing rules

Canonical preflight JSON (`canonical_preflight_json`):

- `json.dumps(..., sort_keys=True, separators=(",", ":"))`
- Non-finite floats are replaced by stable string sentinels:
  - `NaN` → `"NaN"`
  - `+Inf` → `"Infinity"`
  - `-Inf` → `"-Infinity"`
- Tuples normalised to lists.
- `dict` keys are stringified by `sort_keys`.

`verify_capsule_sha256(capsule)` recomputes the sha over the
canonical-JSON of `{k: v for k, v in capsule.items() if k != "sha256"}`
and raises `CapsuleShaMismatch` on disagreement.

`PreflightDecision.sha256` is the canonical-JSON sha over:

```
{
  "launch_allowed": bool,
  "excluded_combos": sorted list of [sid, mid],
  "excluded_cells": sorted list of [sid, mid, N],
  "refusal_reasons": list of strings (preserve discovery order),
  "capsule_shas": {pos_control, neg_control, null_audit, smoke_test → sha or "UNVERIFIED"}
}
```

Same inputs → bit-exact identical decision sha across calls,
processes, machines.

## Required tests

The preflight contract is pinned by 48 tests across two suites:

- `tests/research/systemic_risk/test_d002c_preflight.py` (33 tests)
- `tests/research/systemic_risk/test_d002c_sweep_runner_preflight_integration.py` (15 tests)

Plus the legacy `tests/research/systemic_risk/test_d002c_sweep_runner.py`
suite (37 tests), unchanged in assertions, must continue to pass under
`require_preflight=False` legacy-shim mode.

## CI requirements

The PR's `measurement_command` runs `mypy --strict
--follow-imports=silent`, `ruff check`, `black --check`, and `pytest`
on the four edited Python files plus the legacy suite. All four gates
must be green before merge.

## Rollback command

```bash
git revert <commit-sha>
```

Or, to reproduce the manual rollback:

```bash
git checkout HEAD~1 -- \
  && rm -f research/systemic_risk/d002c_preflight.py \
     tests/research/systemic_risk/test_d002c_preflight.py \
     tests/research/systemic_risk/test_d002c_sweep_runner_preflight_integration.py \
     docs/governance/D002C_PREFLIGHT_CONTRACT.md \
     .claude/commit_acceptors/x10r-d002c-preflight-enforcement.yaml
```

The legacy-shim edits in `tests/research/systemic_risk/test_d002c_sweep_runner.py`
are restored by the `git checkout HEAD~1 --` step.

## Known limitations

1. **Null-audit capsule schema is C2.4-D-defined.** The null-audit
   module (`d002c_null_audit`) emits per-cell `NullAuditResult`
   payloads but does not currently write an aggregate capsule. The
   preflight requires a wrapper of `kind:
   d002c_null_audit_capsule_v1` containing a `results: list[...]`
   field. An orchestrator (or a future C2.4-C addendum) is responsible
   for producing this wrapper. The preflight refuses launch if the
   wrapper is absent — there is no fallback.

2. **Smoke capsule kind is structural.** The smoke-test writer emits
   no `kind` field. The preflight identifies the smoke capsule by the
   presence of the canonical field set. This is the writer's emitted
   shape; the preflight matches it verbatim.

3. **POS / NEG exclusions are non-veto.** A non-empty
   `excluded_combos` or `excluded_cells` reduces the grid but does
   not refuse launch. This is by design — gating on "any exclusion at
   all = refuse" would void the purpose of the controls (which are
   themselves grid-reducers).

4. **Per-cell preflight identity is not bound to per-cell sweep
   identity.** The preflight verifies substrate / metric / N
   identities against the global registries. It does **not** verify
   that every preflight cell's identity matches a sweep grid cell;
   the converse direction (sweep grid → preflight) is enforced via
   the pre-registration's lock on the same registries.

5. **The preflight does not check inter-capsule consistency** beyond
   identity — e.g. it does not refuse if POS and NEG report conflicting
   verdicts on the same combo. The science-layer reading of "POS PASS
   + NEG EXCLUDE on the same combo" is for the sweep result reader to
   interpret, not the launch gate.

## Claim boundary

This module is **claim-neutral**. It does not produce, promote, or
endorse any scientific claim. Its only output is:

- a frozen `PreflightDecision` consumed by `run_sweep`,
- a tuple of `SkippedCell` records persisted to the checkpoint
  ledger as `SKIPPED_BY_PREFLIGHT` entries.

The sweep result reader (C2.5, pending) is the layer that may
interpret these outputs for claim purposes; the preflight enforcement
layer never does.

Forbidden vocabulary in this document (audit-enforced): "certified",
"validated", "bank-level", "production-ready", "real-data confirmed",
"universal", "proven". Permitted: "preflight-enforced",
"synthetic-only", "fail-closed", "deterministic under fixed inputs",
"claim-neutral", "launch-gating layer".
