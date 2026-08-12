# CALIB-GRID-001 — External Ground-Truth Calibration of the Kuramoto Stack

> **Kind:** pre-registered, fail-closed **calibration** instrument.
> **Not a hypothesis.** **Current verdict: `NEGATIVE`** — see
> `RESULTS.md` for the localized refinement targets.

## What this does

Feeds simulated swing-equation phase data — generated from the
*published* admittance / injection data of the canonical WSCC 3-machine
9-bus IEEE test system — into GeoSync's coupling inverse machinery and
measures how well GeoSync recovers what is already known **exactly**.

Double ground truth (Dörfler & Bullo, PNAS 2013):

1. *Numerical* — `K_true = |V_i||V_j|B_ij`, `ω_true = P_i/d_i` from the
   published IEEE data.
2. *Analytic* — closed-form critical-coupling scale
   `s_crit = ‖B†ω‖_{E,∞}` (Dörfler–Bullo Eq. (3)).

## Pipeline

```
published IEEE data  →  K_true, ω_true        (grid_data.py)
   →  swing-equation θ(t)                      (core.kuramoto.second_order)
   →  GeoSync inverse  →  K̂, ω̂               (core.kuramoto.coupling_estimator)
   →  Frobenius / topology-F1 / ω-err / s_crit-err vs Dörfler–Bullo
   →  frozen pre-registered gates  →  PASS | NEGATIVE
```

## Reproduce

```bash
PYTHONPATH=. python -m research.calibration.grid_kuramoto.run \
    --system wscc9 --out research/calibration/grid_kuramoto/RESULTS.json
# exit 0 ⇒ PASS, exit 1 ⇒ NEGATIVE (fail-closed)
```

`--system ieee39` runs the larger IEEE-39 New England fixture (heavy;
marked `@slow` in the test suite, not part of the WSCC-9 verdict).

## Files

| File | Role |
|---|---|
| `PREREGISTRATION.md` | frozen gates + config, committed before the result ledger |
| `PROVENANCE.md` | citation chain + reduction formulae with equation refs |
| `grid_data.py` | embedded WSCC-9 / IEEE-39 data + reduction functions |
| `calibration.py` | simulate → recover → score loop |
| `gates.py` | single source of truth for the acceptance gates |
| `run.py` | CLI; emits `RESULTS.json` machine-readable ledger |
| `RESULTS.md` / `RESULTS.json` | sha-pinned NEGATIVE artifact + interpretation |

## Verdict discipline

The only terminal labels are `PASS` (every gate green) and `NEGATIVE`.
A `NEGATIVE` is informative: the failing gate's `localises_to` names
the exact estimator stage to refine. No "validated" / "calibrated" /
"passed" language is emitted on partial success.

## References

See `PROVENANCE.md`. Core: Dörfler, F. & Bullo, F. (2013),
*Synchronization in complex oscillator networks and smart grids*, PNAS
110(6):2005–2010.
