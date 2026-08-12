# P0 Roadmap Closure Ledger

Date: 2026-05-29

## Closure principle

A P0 item is closed only when it has all four surfaces:

1. test or executable validator;
2. evidence artifact;
3. claim boundary;
4. fail-closed or explicitly non-promoting gate.

## Local audit snapshot

Commands were run against the uploaded repository archive on 2026-05-29.

| Check | Result |
|---|---:|
| Invariants loaded from `.claude/physics/INVARIANTS.yaml` | 97 |
| Kernel self-check | PASS |
| Physics files scanned | 199 |
| Physics test functions scanned | 2178 |
| Physics-grounded tests | 261 / 2178 (12%) |
| L1 missing INV references | 1917 |
| L2 invalid INV IDs | 17 |
| L3 type mismatches | 63 |
| L4 weak/missing assertion messages | 119 |
| L5 possible magic thresholds | 24 |
| C1 silent clamp/clip issues after this pass | 0 |
| C2 undocumented numeric bounds after this pass | 0 |

## Current state

| Item | Status | Evidence |
|---|---|---|
| 13 historic zero-witness P0 invariants | CLOSED_METADATA_SYNCED | `docs/physics/strict_witness_surface.md`; `.claude/physics/INVARIANTS.yaml` now carries `tests:` metadata for strict T8-T16 witnesses; `docs/physics/evidence_matrix.md` regenerated |
| C1/C2 audit blocking | CLOSED_BLOCKING | C1/C2 audit count is 0; `.github/workflows/physics-kernel-gate.yml` now runs code audit without `|| true` |
| Orphan physics tests below 100 | OPEN | local sweep reports 1917 L1 issues after classifier repair; `docs/physics/P0_MIGRATION_BACKLOG.md` ranks next batches |
| Kelly theory boundary | CLOSED_DOC | `docs/physics/theory/KELLY_THEORY.md` |
| OMS theory boundary | CLOSED_DOC | `docs/physics/theory/OMS_THEORY.md` |
| SignalBus theory boundary | CLOSED_DOC | `docs/physics/theory/SIGNALBUS_THEORY.md` |
| HPC theory boundary | CLOSED_DOC | `docs/physics/theory/HPC_THEORY.md` |
| Criticality FSS battery | PREREGISTERED | `experiments/criticality_fss/README.md` and `schema.json` |
| OOS signed audit artifact | RETIRED_PENDING | existing audit report marks OOS evidence RETRACTED |
| README three-surface split | CLOSED_POLICY_HOOKED | `docs/README_SURFACES.md` defines verified kernel / measured experiments / hypothesis sandbox; README claim boundary links to it |

## Metadata drift status

The previous drift between strict witness files and generated evidence matrix is reduced. The validator classifier was also repaired so `async` no longer matches the `sync` keyword. The matrix is still generated from `.claude/physics/INVARIANTS.yaml`, but strict T8-T16 witness metadata is now represented in the registry and matrix.

## Next machine step

Reduce the L1 backlog by migrating orphan physics tests in batches. The priority order is:

1. tests under `tests/unit/physics/` that touch P0 invariants;
2. neuro-controller tests with existing invariant semantics but missing docstring IDs;
3. integration tests touching physics paths;
4. shape/schema tests that should be moved out of physics paths or explicitly marked non-physics.

## Promotion rule

No README headline may claim live alpha, verified physical markets, or criticality until the corresponding artifact passes the claims-evidence gate.
