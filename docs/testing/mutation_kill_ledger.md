# Mutation kill ledger

Source-of-truth: [`.claude/mutation/MUTATION_LEDGER.yaml`](../../.claude/mutation/MUTATION_LEDGER.yaml)
Tests: [`tests/mutation/test_mutation_ledger.py`](../../tests/mutation/test_mutation_ledger.py)

Two harnesses feed the ledger:

- **Physics** — [`tools/physics_mutation_check.py`](../../tools/physics_mutation_check.py)
  (pre-existing; physics-invariant mutants: Arrow / Bekenstein /
  failure_axes / observer bandwidth / cosmological / simulation
  falsification).

- **Calibration layer (security)** —
  [`tools/mutation/security_mutation_check.py`](../../tools/mutation/security_mutation_check.py)
  (new; covers the gates introduced by this calibration layer:
  dependency-truth unifier, evidence-matrix validator, claim-ledger
  validator).

## Why this exists

A test that passes after a mutation does not actually test what it
claims to test. The mutation kill ledger is the load-bearing answer to
"do these tests catch what they claim to catch?" — for both physics
invariants and the calibration gates we have just shipped.

## Ledger schema

```yaml
- mutant_id: dep_policy_accepts_torch_drift
  harness: security_mutation_check
  target_file: tools/deps/validate_dependency_truth.py
  mutation: |
    validate_dependency_truth treats requirements.txt floor below the
    pyproject floor as fine — F01 regression slips past the gate.
  expected_killing_test: tests/deps/test_validate_dependency_truth.py::test_d1_detects_pyproject_above_requirements
  killed: YES
  last_run_command: python tools/mutation/security_mutation_check.py --mutant dep_policy_accepts_torch_drift
  last_run_status: 0
  restore_verified: YES
  notes: ""
```

## Mutants currently registered (10 total)

### Physics (6) — owned by `tools/physics_mutation_check.py`

| ID | Target | Mutation |
|---|---|---|
| `anchored_ignores_arrow` | `core/physics/anchored_substrate_gate.py` | drops Arrow axis |
| `anchored_ignores_bekenstein` | `core/physics/anchored_substrate_gate.py` | drops Bekenstein axis |
| `failure_axes_drops_arrow` | `core/physics/anchored_substrate_gate.py` | failure list reports only one cause |
| `bandwidth_inverted` | `core/physics/observer_bandwidth.py` | Γ ≥ Σ̇ becomes Γ ≤ Σ̇ |
| `cosmo_above_passes` | `core/physics/cosmological_compute_bound.py` | over-ceiling claim silently passes |
| `sim_threshold_inverted` | `core/physics/simulation_falsification.py` | strict > becomes < |

### Calibration layer (4) — owned by `tools/mutation/security_mutation_check.py`

| ID | Target | Mutation |
|---|---|---|
| `dep_policy_accepts_torch_drift` | `tools/deps/validate_dependency_truth.py` | F01 regression slips past D1 |
| `dep_policy_accepts_strawberry_below_fix` | `tools/deps/validate_dependency_truth.py` | F03 regression slips past D2 |
| `evidence_validator_allows_scanner_to_imply_exploit` | `.claude/evidence/validate_evidence.py` | drops both OVERCLAIM_REFUSED checks (per-category + cross-category) |
| `claim_ledger_allows_fact_with_no_falsifier` | `.claude/claims/validate_claims.py` | drops the NO_FALSIFIER rule |

All four calibration mutants killed on the latest run; working tree
clean afterwards (verified by `git diff --exit-code`).

## Required mutants vs. delivered

The TASK 6 brief requested seven mutants:

1. anchored gate ignores Arrow                 → `anchored_ignores_arrow` ✓
2. anchored gate ignores Bekenstein            → `anchored_ignores_bekenstein` ✓
3. failure_axes drops second failure           → `failure_axes_drops_arrow` ✓
4. dependency policy accepts torch drift       → `dep_policy_accepts_torch_drift` ✓
5. dependency policy accepts strawberry below  → `dep_policy_accepts_strawberry_below_fix` ✓
6. evidence validator scanner→exploit          → `evidence_validator_allows_scanner_to_imply_exploit` ✓
7. claim ledger FACT with no falsifier         → `claim_ledger_allows_fact_with_no_falsifier` ✓

All seven delivered. Three additional physics mutants
(`bandwidth_inverted`, `cosmo_above_passes`, `sim_threshold_inverted`)
were already shipped by the pre-existing harness and remain in the
ledger.

## Running

```bash
# Physics:
python tools/physics_mutation_check.py --list
python tools/physics_mutation_check.py --all --fail-on-survivor

# Security / calibration:
python tools/mutation/security_mutation_check.py --list
python tools/mutation/security_mutation_check.py --all --fail-on-survivor

# Single mutant:
python tools/mutation/security_mutation_check.py --mutant claim_ledger_allows_fact_with_no_falsifier
```

Exit codes (consistent across both harnesses):

| Code | Meaning |
|---|---|
| `0` | all named mutants killed (or restored cleanly with no survivor) |
| `1` | at least one mutant survived AND `--fail-on-survivor` set |
| `2` | restore failed for any mutant — HARD FAIL, possibly dirty tree |
| `3` | pattern not found for any mutant (skipped, not killed) |
| `4` | invocation error |

After every run, the harness asserts `git diff --exit-code` returns 0.
A killed mutant that leaves a dirty tree is treated as a harder failure
than a survived mutant.

## How the harness works

1. Read the source file.
2. Apply the text substitution (single occurrence by default; the
   `replace_all` flag triggers global substitution for cases where a
   single edit is insufficient — e.g. when the same guard appears at
   two call sites).
3. Run the expected killer test via `pytest`.
4. Restore the source via `git checkout HEAD -- <path>`.
5. Verify clean state via `git diff --exit-code` on the file.
6. Classify the outcome: KILLED / SURVIVED / NOT_FOUND / RESTORE_FAILED.

## Tests for the ledger

- `tests/mutation/test_mutation_ledger.py` validates:
  - the ledger schema (every entry has the required keys)
  - the target_file and expected_killing_test paths exist
  - the harness names match the actual harness modules
  - ≥5 mutants are marked `killed: YES` with `restore_verified: YES`
  - the security harness ID set matches the ledger's security entries
  - **end-to-end:** the security harness runs all 4 calibration mutants
    against the live tree and exits 0 with a clean working tree

## What the ledger does NOT promise

- It does NOT promise full mutation coverage of the codebase. It is a
  hand-curated set of mutations targeting the load-bearing gates.
  Comprehensive coverage would require a real mutation-testing tool
  (mutmut / cosmic-ray) configured per-module.
- It does NOT replace integration tests. A mutation harness only proves
  that named tests catch named regressions; it cannot find unknown bugs.
- It does NOT exercise unsubstituted code paths. If a mutation is on a
  line that never executes during the killer test, the harness will
  report SURVIVED; the right fix is to choose a more central mutation
  target, not to weaken the killer test.

## Origin

Same arc:

- The physics harness predates the calibration layer; it was already
  shipping six mutants for the physics-invariant gates.
- The 2026-04-26 audit added the calibration layer (claim ledger,
  evidence matrix, dependency-truth unifier). Each gate needed its own
  mutation kill regression test, both to prove the gate works AND to
  give future contributors a documented pattern for adding more.
- The central ledger unifies the two harnesses so a single
  YAML / pytest run can attest to mutation coverage across the whole
  invariant set.
