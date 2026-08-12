# P0 Local Execution Report — 2026-05-29

## Scope

Local zip-based audit pass over `GeoSync-main`.

## Commands executed

```bash
python .claude/physics/validate_tests.py --self-check
python scripts/count_invariants.py
python .claude/physics/validate_tests.py tests/ --summary
python .claude/physics/validate_tests.py core/ --audit-code --summary
python tools/physics_evidence_matrix.py --out docs/physics/evidence_matrix.md
```

## Results

| Check | Result |
|---|---:|
| Invariants loaded | 97 |
| Kernel self-check | PASS |
| Strict T8-T16 validator | 11/11 PASS |
| C1 before patch | 6 |
| C1 after patch | 0 |
| C2 after patch | 0 |
| Physics files scanned | 199 |
| Physics test functions | 2178 |
| Grounded physics tests | 261 |
| Grounding fraction | 12% |
| Remaining validator issues | 2140 |

## Environment limitation

Strict pytest execution was blocked by the local sandbox dependency mismatch: repository requires `pandas >= 2.3.0`, sandbox has `pandas 2.2.3`.

## Engineering conclusion

The next liquid project target is not more claims. It is grounding-density closure: reduce L1 orphan tests, fix invalid invariant IDs, remove type mismatches, and keep C1/C2 blocking only after zero audit issues.
