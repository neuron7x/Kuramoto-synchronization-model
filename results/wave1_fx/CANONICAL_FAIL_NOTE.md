# Wave 1 · combo_v1 × 8 FX — CANONICAL FAIL NOTE

> **combo_v1 is falsified on the 8-FX daily cross-sectional panel under
> locked Wave 1 preregistration. No Wave 2 is authorized. Any continuation
> on FX requires a new FX-native signal family and a new preregistration,
> not parameter rescue.**

## 1. Experiment identity

| field | value |
|---|---|
| line_id | `combo_v1_fx_wave1` |
| signal_family | `combo_v1` |
| signal source (frozen) | `research.askar.full_validation.build_signal` |
| signal parameters (frozen) | `window=120, threshold=0.30, col="combo"` |
| GeoSync SHA at lock | `8b68156df48f1d8ec7566a8db57fb71a66cf8622` |
| substrate | 8-asset daily close at 21:00 UTC, inner-join |
| universe | EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, EURGBP, EURJPY |
| OOS window | 2008-01-02 → 2026-02-09 |
| OOS bars | 4704 trading-day bars |
| folds | 222 (all valid) |
| position rule | cross-sectional L/S: +0.5 top-2, −0.5 bottom-2, 1-bar lag |
| costs (verdict run B) | 1.0 bps EURUSD/GBPUSD/AUDUSD; 1.5 bps others |

## 2. Preregistration artefacts

| artefact | SHA |
|---|---|
| lock SHA (pre-run) | `ef0b774bc4aeb093b843d9494d3b13612ab63e59` |
| complete SHA (post-run) | `3214612f59b56059c7b9a668baec047e1f0c793a` |

Evidence directory: `results/wave1_fx/`.

## 3. Final verdict

**FAIL** (per `results/wave1_fx/run_b_net/summary.json` — verdict run).

| gate | value | threshold | pass |
|---|---:|---:|:---:|
| median fold-median Sharpe | −0.0457 | ≥ 0.80 | FAIL |
| % folds with positive median Sharpe | 43.2 % | ≥ 60 % | FAIL |
| 2022 folds median Sharpe (n=15) | +0.1964 | ≥ 0 | pass |
| max drawdown (OOS portfolio) | 0.4488 | ≤ 0.20 | FAIL |

3 of 4 gates fail decisively. Per `PREREG.md §4` the verdict is binary
and no gate subsetting is permitted.

## 4. Why Wave 2 is forbidden

`PREREG.md §GATE`: *"Wave 2 starts only on PASS verdict. FAIL → root
cause analysis → redesign or stop."*

`PREREG.md §8 (forbidden after lock)`: change universe, change signal
parameters, change position rule, exclude valid folds, re-run with
different window after seeing results, report best-asset subset.

Any path that keeps the **same signal family (`combo_v1`) on the same
substrate (8-FX daily panel)** and attempts to reach PASS by:

- widening/narrowing the rolling window,
- retuning the 0.30 edge threshold,
- switching lag,
- changing the L/S cardinality (top-k / bottom-k),
- swapping the metric from median to some other aggregate,
- excluding the failing folds,

is **parameter rescue** within a falsified line and is prohibited.

## 5. Exact closure statement (canonical, verbatim in all downstream citations)

> combo_v1 is falsified on the 8-FX daily cross-sectional panel under
> locked Wave 1 preregistration. No Wave 2 is authorized. Any
> continuation on FX requires a new FX-native signal family and a new
> preregistration, not parameter rescue.

## 6. Explicit prohibitions (enforced by registry + tests)

| action | allowed? |
|---|:---:|
| Continue combo_v1 on 8-FX substrate with any parameter change | **NO** |
| Re-run combo_v1 on 8-FX substrate with different window / threshold / lag | **NO** |
| Reuse Wave 1 preregistration for a follow-on run | **NO** |
| Subset the 8-FX universe and re-run combo_v1 | **NO** |
| Raise 2022-touching folds above the other 3 failing gates | **NO** |
| Invoke "promising", "almost works", "needs tuning" language | **NO** |
| Start a new preregistration with a new FX-native signal family | YES (requires fresh pre-reg, fresh lock, fresh fold manifest) |
| Apply combo_v1 to a non-FX substrate | YES (separate line_id; must carry its own fail-closed contract) |

## 7. Cross-references

- `results/wave1_fx/PREREG.md` — the locked contract
- `results/wave1_fx/VERDICT.md` — machine-generated verdict
- `results/wave1_fx/ROOT_CAUSE.md` — evidence-tiered root-cause
- `results/wave1_fx/POSTMORTEM_SUMMARY.md` — decision-grade synthesis
- `results/wave1_fx/audits/` — topology / null / exposure audits
- `config/research_line_registry.yaml` — machine-readable closure
- `tests/test_research_line_registry.py` — enforcement tests
