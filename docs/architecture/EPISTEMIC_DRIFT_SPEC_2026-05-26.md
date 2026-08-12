# Epistemic Drift Guard Specification v1.0 (2026-05-26)

## 1. Problem statement
The repository must fail-closed when invariant-count claims drift between documentation and executable registry state.

## 2. Falsifiable hypothesis
If any checked source reports a different invariant count than the executable counter, `check_epistemic_drift` returns exit code `1`.

## 3. Scope
- Sources under control:
  - `README.md` badge/statement count
  - `CLAIMS.md` claim row `C-INV-COUNT`
  - `scripts/count_invariants.py` executable count
- Out of scope:
  - Non-invariant claims
  - Historical archived docs

## 4. Interface contract
### Inputs
- Repository filesystem state at invocation time.

### Outputs
- `stdout`:
  - success: `OK: invariant counts synchronized at <N>`
  - failure: prefixed with `EPISTEMIC DRIFT DETECTED:` and per-source values
- Exit code:
  - `0` on synchronized state
  - `1` on mismatch or missing required claim id/data

### Determinism
- No network I/O.
- Same tree state => same result.

## 5. Invariants
1. `C-INV-COUNT` must exist in `CLAIMS.md`.
2. `README_count == CLAIMS_count == COUNT_SCRIPT_count`.
3. Drift metric `Δ = max(counts) - min(counts) == 0`.

## 6. Execution policy
- CI: `.github/workflows/check_epistemic_drift.yml` on every PR and push to `main`.
- Local: pre-commit hook `epistemic-drift-check`.

## 7. Failure handling
- Fail-closed: block merge/commit path when drift detected.
- Operator action: sync docs or invariant registry, then rerun check.

## 8. Verification mapping
- Unit parser checks: `tests/tools/test_check_epistemic_drift.py`.
- End-to-end check: `python scripts/check_epistemic_drift.py`.

## 9. Success criteria
- `Δ = 0` in CI and local checks.
- Check runtime target: < 2s on standard CI Linux runner.

## 10. Rollback
- Revert:
  - `scripts/check_epistemic_drift.py`
  - `.github/workflows/check_epistemic_drift.yml`
  - pre-commit hook entry
