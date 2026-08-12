# LIMITATIONS — research/systemic_risk

> What the instrument does NOT claim, in deliberate detail.

## 1. Domain limitations

* **No real-data run yet.** Every `HARD_PASS` and `HARD_FAIL` so far
  is on synthetic stand-ins. `C-SYSRISK-PHASE` remains
  `HYPOTHESIS`-tier per `CLAIMS.md`.
* **No mechanism claim.** Phase-locking *correlation* with crisis
  onset would be associational. A causal claim requires:
  – a pre-registered intervention experiment on a sandbox
    interbank simulator (Battiston et al. 2012-style), AND
  – a replicated detection on at least one out-of-sample crisis
    not in the training set.
* **Network coverage.** e-MID is Italy-only; BIS LBS is
  jurisdiction-aggregated, not bank-level. Any `MEASURED` claim
  must explicitly state which fraction of the global interbank
  graph the dataset covers and how stress in the un-observed
  fraction would invalidate the score.

## 2. Statistical limitations

* **Small N of crises.** Bonferroni at k=3 crises gives
  α_per_crisis ≤ 0.0033 for a family-wise α=0.01. Below 3 valid
  pre-event windows the verdict is structurally `UNDECIDED`.
* **Bootstrap CI undercoverage.** Percentile bootstrap is known to
  under-cover at small n_pos / n_neg (Efron-Tibshirani 1993,
  ch. 14). Real coverage at n_pre_event ≈ 60 may sit at 0.92–0.93.
  The protocol's binomial-derived acceptance bound accounts for
  this — but consumers should not over-interpret a CI that
  *just barely* clears 0.70.
* **No walk-forward yet.** Out-of-sample validation requires
  fixing the score's hyperparameters on a strict training subset
  before any test-set crisis is touched. Until that infrastructure
  lands, every fit is in-sample by construction.

## 3. Modelling limitations

* **Sakaguchi α frozen at zero.** Per-pair phase lag matrices are
  scaffolded (`coupling.sakaguchi_alpha_zero`) but not estimated.
  Joint estimation lives in `core.kuramoto.frustration` and is
  expensive — engaging it on real data is a separate experiment.
* **First-order ω estimator.** `coupling.omega_from_volatility`
  uses sample-σ × 2π·fs as a stand-in for the dominant
  spectral-power frequency. The proper estimator (Lomb-Scargle on
  rolling-vol time series) is in `core.kuramoto.natural_frequency`
  and is substantially more expensive; switching is a flag-day
  decision that requires re-running the full battery.
* **Static ledger.** The default banking-crisis ledger is
  Laeven-Valencia 2018 + two post-2020 designations. Country
  coverage is Western + 2023 anchors only; emerging-market
  crises (e.g. 2018 Turkey, 2018 Argentina) are deliberately
  out of scope until a separate pre-registration covers them.

## 4. Engineering limitations

* **Editable-install drift.** The `scripts/export_governance_schemas.py`
  helper in this repository is sensitive to the local Python
  `sys.path` ordering when an editable `geosync` package is
  installed elsewhere. The CI environment is clean and
  unaffected, but local developers running `--check` should
  invoke the script via `python -m` to bypass the issue.
* **JAX engine import.** `core/kuramoto/jax_engine.py` carries 5
  pre-existing `mypy --strict` errors on `origin/main`; they are
  out of scope for this module's own quality gate.

## 5. Causal claims requiring further evidence

A future `VALIDATED` claim must additionally provide:

1. A counterfactual experiment on a closed-form sandbox network
   (e.g. cascade-of-failures simulator) showing that *removing*
   the directed-coupling structure removes the detection.
2. A second-detector cross-check using a non-Kuramoto proxy
   (the linear-correlation surrogate is the obvious A/B
   counterpart) to rule out coherence-only explanations.
3. A pre-registered prospective experiment: lock the detector,
   wait for the *next* major banking-crisis designation, score
   the pre-event window blindly. Result tagged before the
   designation is announced.

Until points 1-3 are in evidence, no claim stronger than
"associative pre-event signal" is permitted in any external
artefact.

## 6. Outstanding gaps (post-2026-05-08 self-audit)

The following items from the Protocol X-7 33-task upgrade
checklist are **not** closed by autonomous code changes and
require external resources or human action:

* **Task 13 — Real-data ingest pipeline.** e-MID is licence-restricted
  (BAFFI / Carefin Bocconi). ECB MMSR is governed by ECB Regulation
  2014/1333 and not freely redistributable. Until a data-sharing
  agreement is signed or a public substitute is identified, the
  CLI's `--data real` path is intentionally absent.
* **Task 14 — Evaluation on 2008 / 2011 / 2020.** Blocked by
  Task 13. The pipeline infrastructure (firewall + leakage +
  ladder + capsule + ledger + FSM + orchestrator + CLI) is
  ready to receive real data; no code change is required to
  run, only the data feed.
* **Task 15 — AUC > 0.75 on real data.** Blocked by Task 13.
  Per the no-unprovenanced-percentages contract, the lab does
  not predict an AUC value before measurement.
* **Task 16 — Zenodo publication of replication capsule.**
  Requires the user's Zenodo account credentials; outside the
  repository scope.
* **Task 17 — Daily SHA256 verification of real-data runs.**
  Blocked by Task 13. The capsule comparator
  (``compare_run_outputs``) ships the per-run primitive; the
  daily-cron wiring is ops, not research code.
* **Tasks 27, 28 — External adversarial review.** Two-to-three
  external reviewers must be invited by the lab; the codebase
  is ready for review (530+ tests, mypy --strict, ruff/black
  clean, property-based coverage of lattice axioms,
  Cramér-Rao bound, Lindley penalty, all eight firewall gates).
