# DRO-ARA v7 — Deterministic Recursive Observer + Action Result Acceptor

Statistical regime observer for price series. Estimates the Hurst exponent via
DFA-1 on log-returns, confirms stationarity with a lag-augmented ADF test, and
emits a deterministic regime classification plus a bounded trading signal
through an ARA feedback loop.

`core.dro_ara` is fail-closed by design: degenerate input raises
`ValueError`, never silent `NaN` propagation.

## Table of contents

1. [Public API](#public-api)
2. [Invariants](#invariants)
3. [Complexity](#complexity)
4. [Empirical IC](#empirical-ic)
5. [Benchmarks](#benchmarks)
6. [References](#references)

## Public API

```python
import numpy as np
from core.dro_ara import geosync_observe

price = 100.0 + np.cumsum(np.random.default_rng(42).normal(size=2048))
verdict = geosync_observe(price, window=512, step=64)
print(verdict["regime"], verdict["signal"], verdict["gamma"])
```

The returned mapping contains (all numeric values are rounded to six decimal
places for deterministic replay):

| Field          | Type  | Meaning                                                   |
| -------------- | ----- | --------------------------------------------------------- |
| `gamma`        | float | Power-law exponent, `2·H + 1`.                            |
| `H`            | float | DFA-1 Hurst exponent on log-returns.                      |
| `r2_dfa`       | float | R² of the DFA log-log regression.                         |
| `regime`       | str   | `CRITICAL` / `TRANSITION` / `DRIFT` / `INVALID`.          |
| `risk_scalar`  | float | `max(0, 1 − |γ − 1|)`, `0` under `INVALID`.               |
| `stationary`   | bool  | Outcome of the lag-augmented ADF test at 5%.              |
| `signal`       | str   | `LONG` / `SHORT` / `HOLD` / `REDUCE`.                     |
| `free_energy`  | float | Mean variational energy over the last `STABLE_RUNS` iterations. |
| `free_energy_circuit_breaker` | bool | `True` iff free energy exceeds the dynamic threshold. |
| `dynamic_free_energy_threshold` | float | Context-conditioned threshold derived from H/R²/risk state. |
| `belief_mean` | float | Recursive Gaussian recognition mean for `gamma`. |
| `belief_variance` | float | Recursive Gaussian recognition variance for comparator error. |
| `causal_chronology_hash` | str | SHA-256 hash-chain tip for internal ARA event ordering. |
| `recovery_action` | str | `ALLOW_MODEL_UPDATE`, `EXPAND_CONTEXT`, or `REDUCE_RISK` from bounded generative recovery. |
| `ara_steps`    | int   | Number of ARA updates executed; retained error/energy buffers are bounded to `STABLE_RUNS`. |
| `converged`    | bool  | `True` iff ARA reached `STABLE_RUNS` consecutive hits.    |
| `trend`        | str\|None | `CONVERGING` / `STABLE` / `DIVERGING`.                |
| `alpha_ema`    | float | EMA gain `2 / (N + 1)`, with `N = (len − window) / step`. |

Other exported names: `derive_gamma`, `risk_scalar`, `classify`, `State`,
`Regime`, `Signal`, and the numeric constants documented in the invariant
table below.

## Invariants

| Invariant                    | Rule                                                                    |
| ---------------------------- | ----------------------------------------------------------------------- |
| `gamma = 2·H + 1`            | Derived; never assigned independently.                                  |
| `risk_scalar ∈ [0, 1]`       | `max(0, 1 − |γ − 1|)`; set to `0.0` when regime is `INVALID`.           |
| `regime = INVALID`           | ADF fails to reject H₀ **or** DFA R² < `R2_MIN` (0.90).                 |
| `regime = CRITICAL`          | Stationary, R² ≥ 0.90, `H < H_CRITICAL` (0.45).                         |
| `regime = TRANSITION`        | Stationary, R² ≥ 0.90, `H_CRITICAL ≤ H < H_DRIFT` (0.55).               |
| `regime = DRIFT`             | Stationary, R² ≥ 0.90, `H ≥ H_DRIFT`.                                   |
| `signal = LONG`              | `CRITICAL` **and** `rs > RS_LONG_THRESH` (0.33) **and** trend ∈ {CONVERGING, STABLE}. |
| `signal = SHORT`             | `DRIFT` **and** trend = `DIVERGING`.                                    |
| `signal = HOLD`              | Default when trend ∈ {CONVERGING, STABLE} and `LONG` guard not tripped. |
| `signal = REDUCE`            | Otherwise — includes all `INVALID` and diverging paths not covered.     |
| Variational free-energy proxy | Gaussian surprise + complexity over comparator error and belief state. |
| Dynamic circuit breaker       | If `free_energy > dynamic_free_energy_threshold`, force `INVALID`, `REDUCE`, `rs=0`. |
| Input contract               | 1-D finite non-constant array, length ≥ `window + step`.                |
| Degenerate input             | `ValueError`; never silent repair.                                      |

All bound constants (`R2_MIN`, `H_CRITICAL`, `H_DRIFT`, `RS_LONG_THRESH`,
`ADF_CV_5PCT`, `ADF_MAX_LAGS`, `EPSILON_H`, `STABLE_RUNS`, `MAX_DEPTH`,
`MIN_WINDOW`, `FREE_ENERGY_CRITICAL`, `VARIATIONAL_ENERGY_FLOOR`,
`VARIATIONAL_ENERGY_CEILING`) are exported from the package and must only be
changed together with their test fixtures.

## Complexity

A single `geosync_observe` call is **O(N · log N)** in the input length `N`:

- DFA-1 evaluates at most 16 geometric box sizes, each costing `O(N)`, and the
  regression over `log(sizes)` is `O(log N)` points. Total: `O(N · log N)`.
- The lag-augmented ADF solves at most `ADF_MAX_LAGS + 1 = 5` linear systems of
  rank ≤ 5 on an `O(N)`-sized design matrix. Total: `O(N)`.
- The ARA outer loop terminates at `MAX_DEPTH` (32) windows or upon
  convergence, each window repeating the above on `window` samples.

Memory is linear in `N`; no buffer grows with `MAX_DEPTH` beyond a bounded
tuple of scalars.

## Empirical IC

The pooled FX information-coefficient sweep artifact
(`results/dro_ara_ic_fx.json`) is not yet committed to this branch. When
available, the headline result is:

- Best pooled IC at horizon `h = 4`, value `0.032`, **HEADROOM_ONLY** — not a
  trading verdict.

TODO(dro-ara): commit `results/dro_ara_ic_fx.json` and link it here with the
full per-symbol table once the sweep has been replayed on the frozen FX
panel.

## Benchmarks

Measured on Python 3.12.3, NumPy 2.4.3, Linux x86-64 (lowlatency kernel),
10 repeats + 2 warmup per window, seed 42 OU input of length `window + step`
with `step = 64`. Artifact is regenerable offline (not committed to avoid
detect-secrets FPs on high-entropy replay hashes).

| Window | Length | p50 (µs) | p95 (µs) |
| -----: | -----: | -------: | -------: |
|    256 |    320 |      538 |      568 |
|    512 |    576 |      584 |      619 |
|   1024 |   1088 |      611 |      631 |

Reproduce:

```bash
python3 -m pytest tests/benchmarks/test_bench_dro_ara.py -q
```

The emitted payload records `p50`, `p95`, `mean`, `min`, `max` per window.

## References

- Dickey, D. A., & Fuller, W. A. (1979). *Distribution of the estimators for
  autoregressive time series with a unit root.* Journal of the American
  Statistical Association, 74(366a), 427–431.
- Ng, S., & Perron, P. (2001). *Lag length selection and the construction of
  unit root tests with good size and power.* Econometrica, 69(6), 1519–1554.
- Peng, C.-K., Buldyrev, S. V., Havlin, S., Simons, M., Stanley, H. E., &
  Goldberger, A. L. (1994). *Mosaic organization of DNA nucleotides.*
  Physical Review E, 49(2), 1685–1689.
- MacKinnon, J. G. (1994). *Approximate asymptotic distribution functions for
  unit-root and cointegration tests.* Journal of Business & Economic
  Statistics, 12(2), 167–176.
