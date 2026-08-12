# Null-Path Inventory (Task 01)

Maps every null generator in GeoSync by whether it preserves the structure
(temporal / phase / graph) of the data it challenges, and every claim-bearing
path that consumes null evidence, with an adequacy flag.

This document makes **no scientific or predictive claim**. It is a structural
inventory, machine-checked by
[`tools/validation/check_null_path_inventory.py`](../../tools/validation/check_null_path_inventory.py)
(fail-closed: a listed generator/path file that vanishes fails the gate). The
adequacy verdict ("i.i.d. Gaussian is inadequate for autocorrelated series") is
the empirical finding of
[`tools/validation/audit_gaussian_null_sufficiency.py`](../../tools/validation/audit_gaussian_null_sufficiency.py)
(measured i.i.d. lag-1 acf ≈ 0.008 vs autocorrelated ≈ 0.810).

## Null generators

| Generator | Location | Class |
|-----------|----------|-------|
| `make_gaussian_null` | `analytics/signals/null_baseline.py` | IID (destroys structure) |
| `make_constant_null` | `analytics/signals/null_baseline.py` | IID (degenerate) |
| `make_phase_shuffled_surrogate` | `analytics/signals/null_baseline.py` | STRUCTURE_PRESERVING (phase) |
| `iaaft_surrogate` | `core/kuramoto/falsification.py` | STRUCTURE_PRESERVING (spectrum + amplitude) |
| N1–N10 null families (incl. N3 block-bootstrap, N4 IAAFT, N5 degree-preserving graph) | `research/systemic_risk/nulls/d002j/null_families.py` | STRUCTURE_PRESERVING (mixed) |

The repo already ships structure-preserving nulls; the gap is not their absence
but ensuring i.i.d. nulls are not used where structure matters (Task 03).

## Claim-bearing paths consuming null evidence

| Path | Null used | Adequacy |
|------|-----------|----------|
| `analytics/signals/descriptor_capsule.py` | `make_gaussian_null` | IID — inadequate for autocorrelated data; the capsule is descriptor-only (not a predictor), but a survival statement over it must move to a structure-preserving null |
| `tools/inference/assemble_evidence_bundle.py` | `make_gaussian_null` | IID — synthetic MEASURED_SYNTHETIC demonstration only; a real phase-structured claim must use a structure-preserving null |
| `research/robustness/romano_wolf.py` | bootstrap over supplied losses (`spa_test`) | structure-agnostic (operates on loss differentials) — OK |
| `research/systemic_risk/nulls/d002j/null_families.py` consumers | N1–N10 families | structure-preserving — OK |

## Machine-readable inventory (validated)

<!-- NULL-INVENTORY-DATA -->
```json
{
  "schema_version": 1,
  "generators": [
    {"name": "make_gaussian_null", "path": "analytics/signals/null_baseline.py", "class": "IID"},
    {"name": "make_constant_null", "path": "analytics/signals/null_baseline.py", "class": "IID"},
    {"name": "make_phase_shuffled_surrogate", "path": "analytics/signals/null_baseline.py", "class": "STRUCTURE_PRESERVING"},
    {"name": "iaaft_surrogate", "path": "core/kuramoto/falsification.py", "class": "STRUCTURE_PRESERVING"},
    {"name": "null_families_n1_n10", "path": "research/systemic_risk/nulls/d002j/null_families.py", "class": "STRUCTURE_PRESERVING"}
  ],
  "claim_paths": [
    {"path": "analytics/signals/descriptor_capsule.py", "null": "make_gaussian_null", "adequacy": "IID_INADEQUATE_FOR_AUTOCORRELATED"},
    {"path": "tools/inference/assemble_evidence_bundle.py", "null": "make_gaussian_null", "adequacy": "IID_SYNTHETIC_DEMO_ONLY"},
    {"path": "research/robustness/romano_wolf.py", "null": "spa_test_bootstrap", "adequacy": "STRUCTURE_AGNOSTIC_OK"}
  ]
}
```
