# VALIDATION — research/systemic_risk

> The strongest claim this module supports as of the current commit.
> The README must not assert anything stronger than this file.

## Current claim ledger

| Claim | Tier | Evidence |
|-------|------|----------|
| The instrument exists and is type-safe | `FACT` | `mypy --strict` clean on every module + test file under the package; 125 unit + property tests pass under `pytest -q`. |
| The decision rule is pre-registered and frozen | `FACT` | `PROTOCOL.md` table 3 + `FalsificationConfig` defaults; every threshold is reproduced in the `RunManifest.config_hash`. |
| The lower rail (random scores) does not falsely pass | `MEASURED` | `tests/research/systemic_risk/test_falsification.py::test_random_scores_do_not_pass` + the equivalent end-to-end smoke run from PR #557 (HARD_FAIL at AUC ≈ 0.45). |
| The upper rail (injected pre-event +3σ signal) passes | `MEASURED` | `tests/research/systemic_risk/test_falsification.py::test_injected_signal_passes` — every crisis returns `auc_ci_low ≥ 0.70` and the verdict is `HARD_PASS`. |
| The bootstrap CI is calibrated | `MEASURED` | `tests/research/systemic_risk/test_falsification.py::test_ci_under_h0_contains_half` — coverage clears the binomial-derived lower bound at α_test=1e-3. |
| The MLE α-recovery on synthetic samples matches the input within ±0.20 | `MEASURED` | `tests/research/systemic_risk/test_network_fitting.py::test_recovers_alpha_on_synthetic` with ensemble of 30 seeds. |
| The BA `m`-calibration recovers the generator's `m` to ±1 on `barabasi_albert_null(N=400)` | `MEASURED` | `test_recovers_generator_m_on_ba_null` parametrised over `m ∈ {2, 3, 4}`. |
| All 6 mandatory null baselines are implemented and tested | `FACT` | `null_models.py` + `tests/test_null_models.py` (23 tests). |
| Interbank phase-locking precedes banking-crisis events on real data | `HYPOTHESIS` | **Pending** — blocked on user-supplied e-MID 2009-2015 / BIS LBS / ECB MMSR dump. |

## What `MEASURED` requires from here

1. Real exposure data ingested via `from_exposure_matrix`.
2. Pre-registered `θ` derivation locked before any AUC is computed
   (training-crisis-only or sensitivity-sweep with full disclosure).
3. Falsification battery returns `HARD_PASS` on **≥ 2** independent
   crises from the {2008 GFC, 2011 Eurozone, 2023 SVB/CS} set.
4. Each detected crisis survives **all 6** null baselines:
   `auc_under_null ≤ 0.55` for every baseline.
5. Bonferroni-corrected p ≤ 0.01 across the surviving crisis set.
6. Replicated by an independent runner using only the
   pre-registered config + dataset hash.
7. `git_dirty=False` in the run manifest.

Every individual condition is *necessary*, the conjunction is *sufficient*.
A failure on any one condition reverts the claim to `HYPOTHESIS` and
archives the negative result per `LIMITATIONS.md`.

## What `MEASURED` does NOT confer

* Trade authorisation: no Layer-4 (Generator) downstream consumer is
  permitted to consume this score for execution sizing without a
  separate, independently-audited Layer-2 (Sustainer) gate.
* Forecasting authority: a `MEASURED` claim is a statement about a
  fixed historical sample, not a prediction about the next crisis.
* Causal claim: the signal is associative; mechanistic causation
  requires the additional intervention experiments listed in
  `LIMITATIONS.md` § "Causal claims requiring further evidence".
