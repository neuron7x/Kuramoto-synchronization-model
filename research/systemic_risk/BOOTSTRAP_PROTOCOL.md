# BOOTSTRAP_PROTOCOL — research/systemic_risk

> Why we bootstrap, what we resample, and what the failure mode
> looks like when the bootstrap is unstable.

## Why bootstrap

The Mann-Whitney AUC has a closed-form variance under
distributional assumptions that interbank crisis data violate
(small n, heavy tails, autocorrelated scores). A non-parametric
percentile bootstrap is the conservative-default uncertainty
quantification; the closed-form Hanley-McNeil SE is recorded only
as a sanity check.

## What is resampled

`falsification.auc_bootstrap_ci`: stratified resampling per arm
with replacement.

* `pos = score values inside the pre-event window`
* `neg = score values inside null windows`
* Each bootstrap iteration draws `n_pos` positives with
  replacement and `n_neg` negatives with replacement
  *independently*; sample sizes are preserved exactly.

## What is NOT resampled

* The **set of crises** is not resampled — those are
  pre-registered.
* The **null window selection** is not resampled at the
  bootstrap layer — those windows are sampled once via the
  configured RNG seed during `_null_windows`, and the sample is
  treated as a fixed fact for the bootstrap.
* The **score values themselves** are not perturbed — bootstrap
  resamples observed values, not generative-model parameters.

Mixing these layers is a known source of inflated CI coverage;
keeping them separate is intentional.

## Seed policy

* `FalsificationConfig.seed` (default 42) is the *root* seed for
  the run. `auc_bootstrap_ci` derives its own RNG via
  `np.random.default_rng(seed)`.
* Same root seed + same input arrays + same `n_bootstrap` = same
  CI to bit-exact precision.
* The seed is recorded in the `RunManifest` (see
  `REPRODUCIBILITY.md`).

## Convergence policy

* Default `n_bootstrap = 10000`. Justification: at this resolution
  the percentile quantile estimates have empirical SE of order
  `sqrt(p(1-p)/n_bootstrap) ≈ 0.005` at p=0.95, well below the
  ±0.01 precision used in the pass / fail threshold comparison.
* Lower values are accepted in tests for runtime budget but never
  in the production validation contract.

## Minimum iterations

Hard floor: `n_bootstrap >= 100` (`FalsificationConfig.__post_init__`).
Below this floor the CI is dominated by binomial sampling noise
and the verdict is unreliable.

## CI definition

`(point_estimate, ci_low, ci_high)` where `ci_low` and `ci_high`
are the `(1 - confidence) / 2` and `1 - (1 - confidence) / 2`
empirical quantiles of the bootstrap distribution. Default
`confidence = 0.95`.

Per `PROTOCOL.md § 2`, the `HARD_PASS` threshold is on
`auc_ci_low`, not the point estimate — the **whole** CI must
clear the bar.

## H0 calibration

Validated by `test_falsification.py::test_ci_under_h0_contains_half`:
under H0 (positives and negatives drawn from the same
distribution), the count of CIs containing 0.5 over 100 runs is
Binomial(100, 0.95). The acceptance threshold
`binom.ppf(1e-3, 100, 0.95) = 91` is derived from first
principles, not asserted as a magic number.

## Failure mode: unstable bootstrap

If the per-iteration AUC variance does not stabilise at
`n_bootstrap = 10000` (e.g. `var(AUC_b for b in [5k, 10k])` > 1e-3)
the bootstrap is unstable for the supplied data and the CI is not
trustworthy. The ingest pipeline must reject the run, not
report the CI.

This stability check is **PENDING** until the real-data ingest
lands; today the bootstrap operates on synthetic rails of size
40-80 where instability has not been observed.
