# Earning calibration: measured falsification power for claim falsifiers (2026-07-22)

The weighting layer landed reporting an honest **`calibration_coverage=0.000 (0/22)`** — 22 claims
verdicted SUPPORTED, none with any *measured* falsification power. This is the first payment
against that: four claim falsifiers were logic-mutation-tested with the repo's own
`tools/mutation_probe.py --only-logic`, serially (the probe rewrites source in place and must
never run concurrently), each run verified to restore the tree.

## Measured (4 ANCHORED claims, 1:1 module↔falsifier)
| claim | module | falsifier | kill-rate |
|---|---|---|---|
| hpc-runtime-state-envelope-integrity | `geosync_hpc/runtime_state.py` | test_runtime_state.py | **100.0%** (5/5) |
| hpc-fixed-point-ledger-conservation | `geosync_hpc/ledger.py` | test_ledger.py | **90.9%** (10/11) |
| hpc-indexed-rng-control-flow-free | `geosync_hpc/indexed_rng.py` | test_indexed_rng.py | **88.9%** (8/9) |
| hpc-session-lifecycle-explicit-fsm | `geosync_hpc/session_fsm.py` | test_session_fsm.py | **0.0%** (0/1) ⚠ |

## The finding this layer exists to surface
**`hpc-session-lifecycle-explicit-fsm` is ANCHORED/P1 and the categorical audit verdicts it
SUPPORTED — yet its falsifier kills ZERO mutants.** The one logic mutation in its module
(`session_fsm.py:145 compare Eq→NotEq`) is invisible to the test. A green verdict resting on a
test that cannot fail. The weighting now assigns that SUPPORTED **contribution 0.0** — not by
judgement, but by measurement (`state=MEASURED, value=0.0`), and distinguishable from the merely
`UNMEASURED` claims, which also contribute 0 but for a stated, different reason.

## Effect on the system measure (honest, small)
```
before:  E=0.5000  calibration_coverage=0.000 (0/22)  tier=EXTRAPOLATED
after:   E=0.5518  calibration_coverage=0.182 (4/22)  tier=EXTRAPOLATED
```
E rose only where teeth were *proven*; the tier stays EXTRAPOLATED because 18/22 SUPPORTED claims
remain unmeasured. The measure refuses to promote itself on partial evidence.

## Actionable teeth gaps (survivors = behaviour the suite cannot detect)
- `geosync_hpc/session_fsm.py:145` compare `Eq→NotEq` — **the whole falsifier is blind**; needs a
  test that distinguishes the FSM transition equality.
- `geosync_hpc/ledger.py:295` boolop `Or→And`.
- `geosync_hpc/indexed_rng.py:152` compare `Lt→GtE`.

## Residual (stated, not faked)
18 of 22 SUPPORTED claims still carry **no** measured falsification power; the recorded manifest
(`artifacts/test_strength/mutation.modules.json`, now 7 modules, aggregate 70/140 = 50.0%) covers
risk/sizing core + these four. Extending measurement to the remaining claim modules is the next
increment; until then `calibration_coverage=0.182` and the system tier is EXTRAPOLATED — which is
exactly what the artifact reports.
