# Cross-asset Kuramoto · Robustness v1 limitations

Honest catalogue of what the v1 framework *does not* measure cleanly.
Nothing below is a bug: every entry is a known statistical or data-
access limitation that a reader MUST account for when interpreting
`verdict.json`, `null_summary.json`, or `ROBUSTNESS_RESULTS.md`.

## 1. PSR has no autocorrelation adjustment — **RESOLVED (v1.1, 2026-04-23)**

`research.robustness.cpcv.probabilistic_sharpe_ratio` implements the
Lopez de Prado (2018) Eq. 14.1 PSR. The formula corrects for skewness
(γ₃) and kurtosis (γ₄) of the sample distribution but **does not**
correct for serial correlation in the return stream. Positive first-
order autocorrelation — typical of regime-following strategies —
inflates the effective sample size used in the Sharpe-variance
denominator.

**Resolution.** Implemented HAC-adjusted PSR using the Newey–West
(1987) Bartlett kernel with the Newey–West (1994) automatic bandwidth
`L = floor(4·(T/100)^(2/9))`:

```python
research.robustness.cpcv.probabilistic_sharpe_ratio_hac(
    returns, sr_benchmark=0.0, periods_per_year=252, lag=None,
)
```

Exported from `research.robustness`. Auto-bandwidth helper
`_newey_west_auto_lag(T)` and effective-sample-size helper
`_newey_west_effective_size(r, lag)` are available for
caller-controlled diagnostics.

Empirical result on the frozen v1 bundle (T = 2166 daily log-returns,
auto-lag `L = 7`):

| Estimator | Value | Interpretation |
|-----------|------:|----------------|
| `psr_daily` (naive) | 1.0000 | Saturates Φ from above |
| `psr_hac_daily` (Newey–West) | 1.0000 | Saturation is **not** an artefact of HAC inflation |

The theoretical concern that "HAC would materially lower the PSR"
does not materialise on this strategy's daily returns: the
autocorrelation structure is sufficiently mild that the Newey–West
sum is a small multiplicative correction, well inside the Φ-saturation
plateau. The cpcv_summary.json now carries `psr_hac_daily`,
`psr_hac_pass`, and `psr_hac_lag` alongside the naive fields;
ROBUSTNESS_RESULTS.md prints both rows.

Decision rule is unchanged (`psr_min = 0.95`). Both estimators clear
the threshold; the naive value is retained for comparability with the
v1 bundle, and the HAC value is the decision-grade one under positive
serial correlation.

## 2. Jitter evaluator is `PLACEHOLDER_APPROXIMATION`

`kuramoto_jitter_executor.make_placeholder_evaluator` returns a
smooth quadratic in fractional parameter-space distance scaled by the
anchor Sharpe. This exercises the primitive contract but does **not**
rebuild the strategy under perturbed parameters.

- The row in `ROBUSTNESS_RESULTS.md` shows `N/A`, not ✓.
- `fraction_within_tol_pass` is forced to `False` regardless of raw
  fraction — the decision layer treats placeholder evidence as
  abstention, not a pass.
- Replacing the executor requires access to the raw asset panel (not
  in the frozen bundle); pairing that panel with the frozen parameter
  lock yields a live evaluator.

## 3. LOO-grid PBO has low path count

`results/cross_asset_kuramoto/offline_robustness/leave_one_asset_out.csv`
ships 5 folds × 13 perturbations. Bailey et al.'s CPCV PBO achieves
full statistical power at C(N, k) paths with N ≥ 8. With 5 paths the
PBO estimate has wide confidence intervals; the reported 0.20 is a
point estimate, not a CI-backed lower bound.

A higher-power PBO requires either a richer strategy-parameter grid
(non-frozen; out of scope) or importance-sampled CPCV over an expanded
fold geometry.

## 4. Null families do not include benchmark-matched tests

The single-stream null suite compares the realised Sharpe against
bootstrapped resamples of itself. It does **not** test whether the
strategy outperforms a matched-cost, matched-lag benchmark such as
BF1 equal-weight. That measurement lives in the offline packet
(`benchmark_family.csv`) and is cross-referenced by
`SEPARATION_FINDING.md`.

## 5. Contract covers the frozen bundle only

Everything above operates on `SOURCE_HASHES.json` (28 artefacts) +
`leave_one_asset_out.csv` (inline-hash-verified extension). The framework
does **not** re-run the spike or re-simulate the strategy. It is a
*read-only* audit layer.

## Forward improvements

Any of the five items above can be closed without changing the
existing primitives:

1. HAC-PSR adjustment (Newey–West kernel inside
   `probabilistic_sharpe_ratio`).
2. Live jitter evaluator (raw asset panel + frozen parameter lock).
3. Higher-power PBO (expand LOO grid or import full spike parameter
   sweep).
4. Benchmark-matched null families (import `benchmark_family.csv`).
5. Protocol-level contract covering the live-shadow evidence rail
   (not just the demo bundle).

None of these is required for a valid FAIL or PASS verdict on the
current frozen evidence; each would tighten the confidence interval
around that verdict.
