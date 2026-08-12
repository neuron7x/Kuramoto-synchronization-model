# Expected Critical Findings

> Findings we already know are coming, posted in advance to give
> the reviewer a calibration baseline. If you don't see at least
> one of these on your list, please re-check — it likely means
> we missed flagging another.

## EX-1 — No real-data evaluation

**Category:** release blocker
**Where:** `LIMITATIONS.md § 6`, `claims.yaml C014`
**What:** The instrument has never been run on real interbank
exposure data. Every PASS is on synthetic stand-ins. No measured
AUC, no measured lead-time, no replication on a real banking-crisis
event.

This is not a bug — it is the present scope of the work. Any
release stronger than `v0.9.9-research-integrity-candidate` is
forbidden until this changes.

## EX-2 — Independent rerun pending

**Category:** release blocker
**Where:** `04_KNOWN_LIMITATIONS.md`
**What:** The capsule has been rerun by the same author. An
independent third party has not yet run `bash rerun.sh` from a cold
clone and confirmed bit-identical metrics_sha.

## EX-3 — Cramér-Rao bound is asymptotic

**Category:** weak statistical assumption
**Where:** `bayes_rigorous.py::cramer_rao_alpha_lower_bound`
**What:** The CRLB is attained asymptotically. At small n
(n ≤ 100) the MLE empirical SE may exceed the bound by 10-20%.
The Monte-Carlo verification (n=5000, 200 replicas) confirms
attainment within [95%, 120%] of the bound, but small-sample
inference should treat the bound as a lower-envelope, not a
point estimate.

## EX-4 — Bootstrap CI undercoverage at small n

**Category:** weak statistical assumption
**Where:** `falsification.auc_bootstrap_ci`, `LIMITATIONS.md § 2`
**What:** Percentile bootstrap CI is known to under-cover at small
n_pos / n_neg (Efron-Tibshirani 1993, ch. 14). At n_pre_event ≈ 60,
nominal 95% coverage may be ~92-93%. Acceptance bound is
binomial-derived to compensate.

## EX-5 — Synthetic generator does not match e-MID statistics

**Category:** documentation mismatch (minor)
**Where:** `synthetic.py::generate_panel`
**What:** The generator produces heavy-tailed degree distributions
qualitatively but is not statistically calibrated to e-MID
2009-2015 (Boss et al. 2004). It is a stress-testing fixture for
the pipeline, not a substitute for real data. A reviewer who
treats it as "validated synthetic data" will find its claims
false.

## EX-6 — Public API surface is large

**Category:** API instability hazard
**Where:** `public_symbol_matrix.csv`
**What:** 172 public symbols. Some (e.g. ad-hoc Bayes-factor
forms retained for back-compat alongside the rigorous form) are
deprecated-in-spirit but still exported. A future PR would
collapse to the minimal-front 30-symbol surface.

## EX-7 — Zero CI runs in this packet

**Category:** irreproducible command
**Where:** `REPRODUCIBILITY_CAPSULE/CI_RUN_LINKS.md`
**What:** This release candidate has been merged through GitHub
Actions; the run links are referenced in `CI_RUN_LINKS.md`. A
reviewer should verify the SHA matches the running CI workflow
artefacts before signing off.
