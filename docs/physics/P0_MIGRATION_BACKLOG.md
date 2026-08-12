# P0 Migration Backlog

Date: 2026-05-29

## Local validator snapshot

After classifier repair, the validator scans 199 physics-test files and 2178 test functions.

| Level | Count | Meaning |
|---|---:|---|
| L1 | 1917 | missing `INV-*` reference |
| L2 | 17 | invalid `INV-*` ID |
| L3 | 63 | test structure does not match invariant type |
| L4 | 119 | missing or weak failure diagnostics |
| L5 | 24 | possible magic thresholds |
| Total | 2140 | remaining validation issues |

Physics grounding: 261 / 2178 tests = 12%.

## Batch-1 sidecar migration

Batch-1 uses `.claude/physics/TEST_WITNESS_MAP.json` instead of rewriting large legacy test files. The sidecar is validated by `.claude/physics/validate_witness_map.py`, now wired into `physics-kernel-gate.yml`.

| Batch-1 file | Sidecar status | Remaining risk |
|---|---|---|
| `tests/core/neuro/serotonin/test_serotonin_controller.py` | L1 grounded by function map | L3/L4/L5 still require assertion-level cleanup |
| `tests/unit/test_kuramoto_ricci_composite.py` | L1 grounded by function map | L3/L4 cleanup remains |
| `tests/unit/core/test_kuramoto_modules.py` | L1 grounded by function map | L3/L4/L5 cleanup remains |
| `tests/core/neuro/serotonin/test_serotonin_runtime_safety.py` | L1 grounded by function map | L3/L4 cleanup remains |
| `tests/core/neuro/dopamine/test_invariants.py` | marked `non_physics_file` | no physics witness claim; utility tests remain ordinary implementation tests |

Local batch-1 result before GitHub connector limits: L1 in these five files reduced to zero, repository L1 reduced from 1917 to 1790, total issues reduced from 2140 to 2047, and grounding moved from 12% to 14%.

## Highest-impact files after batch-1

| Rank | File | Why next |
|---:|---|---|
| 1 | `tests/core/neuro/serotonin/test_serotonin_controller.py` | largest remaining mixed L3/L4/L5 surface after sidecar L1 closure |
| 2 | `tests/core/neuro/serotonin/test_serotonin_runtime_safety.py` | runtime safety tests need assertion diagnostics and structure cleanup |
| 3 | `tests/unit/test_kuramoto_ricci_composite.py` | composite tests need L3/L4 cleanup after sidecar grounding |
| 4 | `tests/unit/core/test_kuramoto_modules.py` | module tests need L3/L4/L5 cleanup after sidecar grounding |
| 5 | `tests/research/calibration/test_grid_kuramoto.py` | next high-volume L1 migration target |

## Batch strategy

1. Use sidecar mapping only when it preserves semantic truth and avoids noisy source rewrites.
2. Add direct `INV-*` docstrings when the file is small or the witness role is locally obvious.
3. Do not add `INV-*` IDs to shape, import, config, serialization, latency, or smoke tests unless they really witness a registered invariant.
4. Mark entire files or individual functions as non-physics only when they are implementation utilities, not physics claims.
5. Re-run `python .claude/physics/validate_witness_map.py` and `python .claude/physics/validate_tests.py tests/ --summary` after each batch.

## Current release gate

C1/C2 code audit is clean and blocking. Remaining P0 risk is test-grounding density plus assertion-level validator quality, not production clamp silence.
