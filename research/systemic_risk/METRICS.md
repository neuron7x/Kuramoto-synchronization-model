# METRICS — research/systemic_risk

> AUC alone is insufficient — § 14 of the canonical R&D checklist.

## Required metrics for any positive claim

| Metric | Definition | NaN when |
|--------|-----------|----------|
| `precision` | `TP / (TP + FP)` | `TP + FP == 0` (no predictions) |
| `recall` | `TP / (TP + FN)` | `TP + FN == 0` (no positives) |
| `false_positive_rate` | `FP / (FP + TN)` | `FP + TN == 0` (no negatives) |
| `false_negative_rate` | `FN / (FN + TP)` | `FN + TP == 0` (no positives) |
| AUC | Mann-Whitney U / `(n_pos · n_neg)` | undefined arms |
| AUC bootstrap CI | stratified percentile, n=10000 | < 2 obs per arm |
| Bonferroni-adjusted p | `min(1, m·p)` across crises | n/a |
| `lead_time_days` | first valid pre-event alarm gap | no alarm in window |

## Zero-division policy

NaN, **never** zero. An undefined denominator is a missing
denominator — propagating it as 0 fakes quality on empty data.
Implementation: `metrics.compute_classification_metrics` and
`metrics.compute_lead_time_metrics`.

## Lead-time strict definition

A signal counts as a valid early warning **iff** it fires inside
`[event - max_lead_days, event - min_lead_days]`.

* Same-day signals excluded when `min_lead_days >= 1` (default).
* Post-event signals never count.
* `event_exclusion_days_after` (default 0) provides extra
  post-event masking when needed.
* The first valid pre-event alarm wins; later alarms inside the
  same window are ignored for that event.

The configuration must be **pre-registered** before any AUC is
computed. Selecting the lead window after seeing the AUC table is
a pre-registration violation and forces re-pre-registration on a
fresh branch.

## CI policy

* AUC: stratified percentile bootstrap, `n_bootstrap = 10000`,
  `confidence = 0.95`. Validation contract requires the *whole*
  CI to clear `pass_auc_ci_low` (default 0.70) — point estimate
  alone is insufficient.
* Coverage of the bootstrap CI under H0 is asserted at the
  binomial-derived lower bound `binom.ppf(1e-3, 100, 0.95) = 91`
  per `test_falsification.py::test_ci_under_h0_contains_half`.

## Multiple-testing policy

Bonferroni FWER across crises (`falsification.bonferroni_correction`).
Stricter than BH FDR — chosen because the cost of a false
`MEASURED` promotion is higher than the cost of an undetected
true positive at the small crisis count we operate on.

## What this PR does NOT claim

* No real-data crisis has been scored against this metric stack.
* The lead-time aggregator's behaviour is verified on synthetic
  inputs only.
* `MEASURED` promotion requires every metric above to be reported
  alongside the AUC for every crisis, with the manifest-bound
  reproducibility bundle from `REPRODUCIBILITY.md`.
