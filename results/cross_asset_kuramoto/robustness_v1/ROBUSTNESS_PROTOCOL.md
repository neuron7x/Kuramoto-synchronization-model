# Cross-asset Kuramoto · Robustness v1 protocol

Canonical input derivations and statistical-test protocols used by the
v1 framework. Every value below is fixed by source-controlled code in
`research/robustness/protocols/`; anything that drifts from this file
is a bug in the code, not a licence to edit the file.

## 1. Input-data derivations

### 1.1 Daily strategy returns

The frozen demo bundle ships the cumulative wealth curve
`results/cross_asset_kuramoto/demo/equity_curve.csv::strategy_cumret`
but does **not** ship a raw `net_ret` series. The framework therefore
derives daily returns as mathematically exact **log returns**:

```
r_t = log(strategy_cumret_t) − log(strategy_cumret_{t-1})
```

Log returns are chosen over simple `pct_change` because:

- they are the honest, time-additive representation of a multiplicative
  wealth trajectory (every daily `r_t` satisfies `exp(Σ r_s) = wealth_t`);
- they are symmetric under sign inversion;
- they preserve independence under permutation and resampling, which is
  the contract assumed by the bootstrap null families.

The derivation is implemented once in
`research.robustness.protocols.kuramoto_contract.KuramotoRobustnessContract.daily_strategy_returns`.

### 1.2 Daily benchmark returns

Identical derivation applied to `benchmark_cumret`.

## 2. Bootstrap null families (single-stream)

The null suite operates on a *realised* return stream only; it has no
access to a raw `position × price` signal. The two families below are
the honest Sharpe-level nulls for that input shape.

### 2.1 iid_bootstrap

Sample indices i.i.d. from `[0, n)` with replacement, compute Sharpe on
the resampled vector, repeat `n_bootstrap` times. Note that *plain
permutation* would be degenerate: Sharpe is order-invariant on a given
vector, so permutation preserves it up to floating-point noise and
yields a trivial p → 1. With-replacement sampling changes the realised
mean and std of every draw and is the proper i.i.d. null for a Sharpe
statistic on a single series.

### 2.2 stationary_bootstrap (Politis & Romano 1994)

Geometric-block resample with mean block length 21 bars. Tests for
information content beyond short-horizon autocorrelation.

Both families share a seeded `np.random.default_rng` and emit a
Davison–Hinkley +1 continuity-corrected upper-tail p-value.

## 3. Statistical thresholds

All thresholds are encoded as module-level constants; this section
mirrors the constants, never the other way round. Drift between code
and this section is a bug in the documentation.

| Threshold | Value | Where set | Semantics |
|---|---:|---|---|
| `null_alpha` | 0.05 | `kuramoto_null_suite.NULL_PASS_P_THRESHOLD` | Upper-tail α for either null family |
| `pbo_max` | 0.50 | `kuramoto_cpcv_suite.PBO_PASS_THRESHOLD` | Fold-mirror PBO must be below this |
| `loo_pbo_max` | 0.50 | `kuramoto_cpcv_suite.LOO_PBO_PASS_THRESHOLD` | LOO-grid PBO must be below this |
| `psr_min` | 0.95 | `kuramoto_cpcv_suite.PSR_PASS_THRESHOLD` | Probabilistic Sharpe must exceed this |
| `jitter_floor_ratio` | 0.80 | `kuramoto_jitter_suite.run_kuramoto_jitter_suite` default `fraction_within_tol_pass` | Fraction of jitter candidates within `sharpe_tolerance` (live evaluator only) |
| `sharpe_tolerance` | 0.20 | `kuramoto_jitter_suite.DEFAULT_SHARPE_TOLERANCE` | Absolute |ΔSharpe| band for jitter evaluator |
| `pbo_tautological_n` | 3 | `kuramoto_cpcv_suite.PBO_TAUTOLOGICAL_CUTOFF` | Below this candidate count, PBO is tautological |
| `pbo_weak_n` | 5 | `kuramoto_cpcv_suite.PBO_WEAK_CUTOFF` | Below this candidate count, PBO is weak |
| `null_convergence_tol` | 0.02 | `analysis_null_convergence.CONVERGENCE_TOLERANCE` | Max \|Δp\| across adjacent trial counts for CONVERGED |

Threshold semantics are one-sided unless stated otherwise.
Null-family tests are upper-tail: reject H₀ when *observed* Sharpe is
in the upper α tail of the bootstrap distribution.

## 4. Artefacts written

Every runner invocation writes strictly under
`results/cross_asset_kuramoto/robustness_v1/`:

- `verdict.json` — terminal decision and per-axis booleans
- `cpcv_summary.json` — PBO (fold mirror + LOO grid), PSR, Sharpe
- `null_summary.json` — p-values per family
- `jitter_summary.json` — jitter stability + evaluator mode
- `ROBUSTNESS_RESULTS.md` — human-readable one-page report
- `ROBUSTNESS_PROTOCOL.md` — this document

Nothing is written outside this directory. The frozen SOURCE_HASHES.json
contract covers 28 artefacts and remains hash-verified on every load.
