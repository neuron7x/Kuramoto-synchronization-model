# Calibration batch 3 — the pattern is systemic, not incidental (2026-07-22)

Six more claim module↔falsifier pairs measured (`mutation_probe --only-logic`, serial, tree-restore
verified). Three more measure **zero**.

| claim module | tier | kill-rate |
|---|---|---|
| `geosync/neuroeconomics/reset_wave_distributed.py` | EXTRAPOLATED | **100.0%** (10/10) |
| `core/dro_ara/engine.py` | ANCHORED | 23.8% (10/42) |
| `geosync/neuroeconomics/reset_wave_engine.py` | ANCHORED | 17.3% (9/52) |
| **`scripts/ci/lint_forbidden_terms.py`** | ANCHORED | **0.0%** (0/4) |
| **`geosync_hpc/backtest.py`** | ANCHORED **P0** | **0.0%** (0/13) |
| **`core/neuro/sizing.py`** | ANCHORED | **0.0%** (0/26) |

## The pattern, stated plainly
Across three batches, **seven** claim modules measured at or near zero falsification power while the
categorical audit verdicted every one of their claims `SUPPORTED`:
`session_fsm`, `serotonin_ode`, `dopamine_execution_adapter`, `signal_bus`, `backtest`, `sizing`,
`lint_forbidden_terms`.

They share a shape. Each falsifier asserts that **something happened** — no exception was raised, a
call returned, a file exists — rather than **what the behaviour was**. Concretely, the four already
closed were blind because they asserted:
- the exception **type** but never its message (`session_fsm`),
- that a function **ran** but never its value (`dopamine_execution_adapter`),
- nothing at all about the criterion the claim names (`serotonin_ode`),
- that signals could be published but never which regime resulted (`signal_bus`).

The three new zeros are the same species. `core/neuro/sizing.py` is the sharpest: it backs the
**Kelly cap** claim (INV-KELLY2, "applied fraction ≤ configured cap") — a capital-safety bound — and
**not one of 26 logic mutations** is detected by its falsifier. `geosync_hpc/backtest.py` backs the
P0 bit-identical runtime-seal claim with 0 of 13.

This is no longer a set of incidents; it is a **systemic property of how the suite was written**.
The categorical audit could never have surfaced it — every one of these tests passes. Only the
weighting layer's demand for *measured* teeth exposes it, which is the entire argument for that
layer.

## What this does to the numbers
Manifest now covers **19 modules, 187/394 = 47.46%** aggregate. The aggregate FELL (63.97% → 47.46%)
because measuring more honestly *lowers* a number that was previously computed over a favourable
subset. That drop is the instrument working: coverage bought truth, not score.

## Next, in criticality order (not convenience order)
1. `core/neuro/sizing.py` — capital-safety cap, 26 survivors, zero teeth.
2. `geosync_hpc/backtest.py` — P0 determinism seal, 13 survivors, zero teeth.
3. `reset_wave_engine.py` (52) and `dro_ara/engine.py` (42) — large, low, ANCHORED.
4. `lint_forbidden_terms.py` — 4 survivors.

Each closes by the proven cycle: a test that can actually fail → re-probe → the kill-rate must move
by measurement. Where a survivor turns out to be an equivalent mutant or out-of-claim-scope, that is
recorded as a limit (see REMAINING_TEETH_AND_ATTRIBUTION_2026-07-22.md), never padded.

---

## CORRECTION (same day): one of the three zeros was MY measurement error

`core/neuro/sizing.py` does **not** measure 0%. It measures **88.5% (23/26)**.

The claim `kelly-sizing-cap-enforced` lists **three** evidence modules
(`core/neuro/sizing.py`, `core/neuro/kuramoto_kelly.py`,
`analytics/math_trading/kelly_criterion.py`) but a **single** falsifier
(`tests/analytics/test_kelly_criterion.py::test_single_asset_kelly_closed_form`) which exercises
only the third. My pairing heuristic — *claim's first evidence module × claim's falsifier* — put
`sizing.py` against a test that never imports it, so the probe correctly reported that those
mutants were not detected. The number was right; **the pairing was wrong**, and the conclusion
drawn from it ("the Kelly capital-safety cap has zero teeth") was false.

Re-measured against the module's **own** tests (`tests/unit/neuro/test_sizing.py`,
`tests/unit/neuro/test_kelly_and_risk_parity.py`, `tests/neuro/test_sizing.py`): **23/26 = 88.5%**.

The other two zeros were checked the same way and are **genuine**: both
`tests/geosync_hpc/test_backtest_runtime_reset.py` and
`tests/governance/test_ierd_phase0_yana_response_coverage.py` do import the modules they are paired
with, and are the only test files that do. So `backtest.py` 0/13 and `lint_forbidden_terms.py` 0/4
stand.

### Fourth measured limit: the pairing heuristic
When a claim declares several evidence modules but one falsifier, pairing *any* module with *that*
falsifier can produce a spurious zero. **A zero must be checked for pairing before it is reported
as a teeth gap** — confirm the falsifier actually imports the module, and if it does not, measure
the module against the tests that do.

The systemic finding of this batch survives the correction, with one fewer instance: **six** claim
modules (not seven) measure at or near zero — `session_fsm`, `serotonin_ode`,
`dopamine_execution_adapter`, `signal_bus`, `backtest`, `lint_forbidden_terms`. The Kelly cap is
**not** among them.
