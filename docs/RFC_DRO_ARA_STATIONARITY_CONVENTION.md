# RFC · DRO-ARA v7 · Stationarity Convention

**Status:** PROPOSED — awaiting operator sign-off before code.
**Author:** Yaroslav Vasylenko
**Date:** 2026-04-21
**Scope:** `core/dro_ara/engine.py` · `_adf_stationary`, `State.from_window`, `classify`
**Blast radius:** INV-DRO3 (regime INVALID iff !stationary ∨ r²<0.90)
**Not in scope:** `H_CRITICAL`, `RS_LONG_THRESH`, signal logic, combo_v1.

---

## 1. Empirical trigger

Walk-forward grid search (2026-04-21,
`experiments/dro_ara_calibration/`) produced a degenerate outcome:

| asset            | folds | stationary | %    |
|------------------|------:|-----------:|-----:|
| SPDR S&P 500     |    69 |          1 | 1.4% |
| USA_500_Index    |   150 |          0 | 0.0% |
| XAUUSD           |   286 |          4 | 1.4% |
| 20y Treasury ETF |    70 |          1 | 1.4% |
| Gold SPDR        |    70 |          2 | 2.9% |
| AUDUSD           |   297 |         14 | 4.7% |
| EURUSD           |   301 |         15 | 5.0% |
| EURGBP           |   297 |         21 | 7.1% |

Across all 7×11 grid cells on SPDR: **0 gate-on folds**. On EURGBP (best
case): top-cell mean OOS Sharpe 0.019 with 2 gate-on folds — fails all
three rejection filters (Sharpe ≥ 0.80, dd ≤ 0.25, trades ≥ 20).

The (H, rs) thresholds are **not** the binding constraint — the upstream
`_adf_stationary(raw_prices)` is.

## 2. Root cause

`_adf_stationary` runs the lag-augmented Dickey–Fuller test on the raw
price series. Asset prices are canonical I(1) processes (unit-root
random walks with drift), so ADF fails to reject H₀ ≈ 95% of the time
on equity indices and ≈ 93–99% on FX/commodities. This is a
mathematically correct classification of the input — but the engine's
downstream contract (INV-DRO4: LONG requires CRITICAL regime AND rs
> threshold) then gates out virtually every real-market trade by
construction, not by parameter choice.

**Asymmetry vs. Hurst path:** `_hurst_dfa` is already internally applied
to `diff(log(price))` (engine.py:138) — i.e. to log-returns, which are
stationary. Only the ADF test is inconsistent: it sees raw prices while
DFA sees returns. The engine currently mixes stationarity conventions.

## 3. Proposed change

Align stationarity test with DFA input. One line in `State.from_window`:

```diff
@classmethod
def from_window(cls, x: NDArray[np.float64] | np.ndarray) -> "State":
    arr: NDArray[np.float64] = np.asarray(x, dtype=np.float64)
-   stat = _adf_stationary(arr)
+   log_returns = np.diff(np.log(np.maximum(np.abs(arr), 1e-12)))
+   stat = _adf_stationary(log_returns)
    g, H, r2 = derive_gamma(arr)
    reg = classify(g, r2, stat)
```

ADF on log-returns matches the Hurst input, matches standard
econometric practice (returns are stationary, prices are not), and
makes INV-DRO3 enforce a non-trivial condition instead of a near-
tautology.

## 4. Invariant audit

| invariant | effect | justification |
|-----------|--------|---------------|
| INV-DRO1 (γ = 2H+1) | unchanged | γ derivation path untouched |
| INV-DRO2 (rs bounds) | unchanged | algebraic, downstream of γ |
| INV-DRO3 (INVALID iff ¬stat ∨ r²<0.90) | **semantics tightened** | now tests returns stationarity, not price-level |
| INV-DRO4 (LONG gate) | more permissive in practice | more windows pass stationarity; H+rs+trend still fully gate |
| INV-DRO5 (fail-closed validation) | unchanged | _validate still rejects NaN/Inf/constant |

## 5. Test impact

Falsification battery (`tests/core/dro_ara/test_falsification.py`):

| test | current expectation | post-change expectation |
|------|---------------------|-------------------------|
| `test_ou_mean_reverting_is_critical` | stationary=True | stationary=True (OU is I(0) in levels AND returns — still passes) |
| `test_random_walk_is_invalid_or_transition` | INVALID or TRANSITION | likely shifts to CRITICAL/TRANSITION: RW returns ARE stationary → needs re-classification of expected regime |
| `test_gbm_with_drift_is_non_stationary` | stationary=False | **GBM drift returns are stationary** → this test will flip. Needs re-framing. |
| `test_signal_never_long_on_gbm` | no LONG | with returns-based ADF, GBM may emit LONG in some stretches; needs revised invariant — LONG-on-GBM acceptable ONLY when H<H_crit captures a short-horizon anti-persistent phase |
| `test_white_noise_prices_are_stationary` | stationary=True | unchanged (prices are stationary, returns also stationary) |
| `test_ou_never_emits_short` | no SHORT | unchanged |

**This is the blast radius.** The change is not a pure equivalence — it
re-interprets what "INVALID regime" protects against. Test suite must
be re-written to express the new contract explicitly, not loosened.

## 6. Alternatives considered

1. **KPSS test on prices** (opposite null) — rejects stationarity more
   readily but introduces a second test convention; adds complexity
   without resolving the mismatch.
2. **Two-stage filter** — require ADF(returns) AND |H−0.5|>ε.
   Equivalent in effect to current-plus-proposed but more code.
3. **Live with 1% activation rate** — honest but leaves the signal path
   dormant on 99% of real-market inputs; contradicts INV-YV1 (living
   gradient). Rejected.

## 7. Rollout plan

1. Merge this RFC to `docs/` (no code change).
2. Separate PR: engine patch + rewritten falsification tests +
   regenerated `experiments/dro_ara_calibration/` artefacts.
3. Third PR (only if Step 2 merges green): re-run threshold grid with
   the fixed engine; propose H/rs calibration on informative grid.

## 8. Fail-closed audit required before merge

Per feedback_fail_closed_audit: any verdict-flipping convention change
must run the operator's full multi-test battery on synthetic + real
fixtures. If any single invariant-violation test goes from PASS→FAIL
post-change, revert. Convention-flips are not free.

## 9. Decision required

- [ ] Approve RFC — proceed to Step 2 (engine patch PR).
- [ ] Amend — specify alternative / tighter scope.
- [ ] Reject — close RFC, leave engine as-is, document the
      high-INVALID-rate as an intentional trade-off in CLAUDE.md.
