# Calibration batch 2 — three P0 neuro modules measure ~zero falsification power (2026-07-22)

Six more claim module↔falsifier pairs measured with `tools/mutation_probe.py --only-logic`
(serial, tree-restore verified after each). The result is the sharpest evidence yet that a
categorical `SUPPORTED` verdict and a *proven* claim are different things.

| claim module | kill-rate | survivors |
|---|---|---|
| `core/neuro/cryptobiosis.py` | 93.8% (15/16) | 1 |
| `core/physics/lyapunov_exponent.py` | 82.1% (23/28) | 5 |
| `research/robustness/cpcv.py` | 45.9% (17/37) | 20 |
| **`core/neuro/signal_bus.py`** | **5.9% (1/17)** | **16** |
| **`core/neuro/serotonin_ode.py`** | **0.0% (0/6)** | **6** |
| **`core/neuro/dopamine_execution_adapter.py`** | **0.0% (0/3)** | **3** |
| `core/kuramoto/ott_antonsen.py` | **UNMEASURED — probe timeout** | n/a |

## The finding
**Three P0-priority neuro modules carry essentially no measured logic-falsification power**, while
the categorical audit verdicts every one of their claims `SUPPORTED`:

- `serotonin_ode.py` **0/6** — the falsifier detects none of six logic mutations, including
  `:176 NotEq→Eq`, `:179 LtE→Gt`, `:181 Gt→LtE` (comparison flips inside the controller's own
  threshold logic) and `:64 Or→And`.
- `dopamine_execution_adapter.py` **0/3** — `:130 Lt→GtE`, `:135 Eq→NotEq`, `:139 Gt→LtE` all
  invisible.
- `signal_bus.py` **1/17** — sixteen survivors, e.g. `:238 Gt→LtE`, `:240 Eq→NotEq`,
  `:241 Or→And`, `:281 LtE→Gt`.

These are the modules behind bounded-veto, RPE-adapter bounds and deterministic fan-out claims.
Their tests pass; the measurement says the tests would keep passing if the comparisons were
inverted. That is precisely the failure mode the weighting layer exists to make visible, and it
was invisible to every gate in the repo until it was measured.

## Honest bookkeeping
- `ott_antonsen.py` is recorded as **UNMEASURED because the probe times out** (its falsifier is a
  heavy chimera simulation), not silently skipped. The weighting already treats an absent record as
  UNMEASURED → contribution 0, so this cannot flatter the score; the reason is stated here.
- Manifest now covers **13 modules, 129/247 = 52.23%** aggregate logic-mutation kill-rate.
- Nothing here changes a claim's categorical verdict. It changes how much that verdict is *worth*.

## Next
Close the gaps in severity order — the two 0% modules first (serotonin, dopamine adapter), then
signal_bus (16 survivors), then cpcv (20). Each closure follows the proven cycle: write a test that
can actually fail → re-run the probe → the kill-rate must move, measured, not asserted.
