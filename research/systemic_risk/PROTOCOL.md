# PROTOCOL — research/systemic_risk

> **Pre-registered falsification protocol for `C-SYSRISK-PHASE`.**
> Frozen at the timestamp on the manifest produced by every run.
> Every parameter below is *load-bearing*; changes require a new
> branch + new pre-registration + re-run from scratch.

## 1. Hypothesis

> The early-warning score derived from the rolling Kuramoto order
> parameter on the directed interbank phase-coupling graph is
> *elevated* in pre-event windows preceding banking-crisis dates
> compared to null windows drawn from the same series at safe
> distance from any event.

## 2. Frozen decision rule

| Verdict | Condition |
|---------|-----------|
| `HARD_FAIL` | ∃ crisis with point AUC ≤ `fail_auc=0.55` OR `auc_ci_low ≤ 0.5 + ci_floor_tol=0.0` |
| `HARD_PASS` | ≥ 2 crises with `auc_ci_low ≥ pass_auc_ci_low=0.70` AND `p_BONF ≤ pass_alpha=0.01` |
| `UNDECIDED` | otherwise |

Bonferroni FWER replaces FDR per the user's strict-control directive.
The whole 95 % bootstrap CI must clear the bar — point estimate alone
is insufficient.

## 3. Frozen pre-registration constants

| Name | Value | Derivation |
|------|-------|------------|
| `pre_event_window_days` | 60 | Brunetti et al. 2019, *J. Banking Finance* 100: 175 — liquidity-stress band ≈ 1/90d–1/5d. |
| `null_window_count` | 30 per crisis | Power: at AUC=0.7 vs 0.5 with α=0.05, n=30 yields ≈ 0.85 power per Hanley-McNeil. |
| `min_distance_from_event_days` | 365 | One full annual cycle — strongest practical separation given quarterly data cadence. |
| `n_permutations` | 5 000 | One-sided permutation p resolves p ≤ 0.001 to ±1 e-4 per Davison-Hinkley +1 continuity. |
| `n_bootstrap` | 10 000 | Stratified percentile bootstrap stabilises the 95 % CI quantile to ±0.005 (Efron-Tibshirani 1993, ch. 13). |
| `confidence` | 0.95 | Industry-standard FWER-compatible level. |
| `fail_auc` | 0.55 | Coin-flip + half-σ at n=60 — anything below is rejection of the signal at the noise floor. |
| `pass_auc_ci_low` | 0.70 | Two-σ separation from chance at n=60: σ_AUC ≈ √(0.05/60) ≈ 0.029, 2σ ≈ 0.058 above 0.55 fail floor. |
| `pass_alpha` | 0.01 | Bonferroni at 3 crises × 0.05/3 ≈ 0.017 → tightened to 0.01 for headroom. |

Every entry is also recorded verbatim in the per-run `RunManifest`
emitted by `replication.build_run_manifest`.

## 4. Mandatory null baselines (§ 8 of the official protocol)

A claimed positive must survive **all six** baselines below.
Implementation: `research.systemic_risk.null_models`.

1. `degree_preserving_randomization` — Maslov-Sneppen on the directed graph.
2. `shuffled_time_labels` — destroys temporal ordering of the score.
3. `random_exposure_weights` — preserves binary support, resamples weights.
4. `static_topology_baseline` — strips temporal evolution of the graph.
5. `linear_correlation_surrogate` — non-Kuramoto coherence baseline.
6. `permuted_crisis_dates` — permutes event labels in time.

The detection AUC under each baseline must drop below `fail_auc=0.55`
for the positive claim to stand.

## 5. Replication contract (§ 13)

Every run emits a `RunManifest` JSON capturing:

* commit SHA + git-dirty flag
* root RNG seed
* deterministic config hash (`sort_keys=True` SHA-256)
* Python + platform info
* runtime-relevant package versions
* full caller config dict
* free-form `extra` (dataset id, data SHA-256, …)

`MEASURED` tier requires a clean (non-dirty) git tree at run time.

## 6. Failure conditions (§ 12)

Any of the below archives the hypothesis as a negative result:

* signal does not lead the crisis;
* signal appears only after the crisis;
* any baseline matches or exceeds the detector;
* result unstable to small parameter changes (sensitivity sweep);
* CI lower bound crosses chance;
* Bonferroni correction kills significance;
* false-positive rate above operational ceiling;
* result hinges on a single dataset;
* second run with the same seed differs.

## 7. Post-detection promotion path

```
HYPOTHESIS
   └─▶ INSTRUMENTED       (this PR)
        └─▶ TESTED_ON_SYNTHETIC      (this PR — both rails verified)
             └─▶ TESTED_ON_REAL_DATA (next PR — blocked on user e-MID/BIS dump)
                  └─▶ MEASURED       (after real-data HARD_PASS on ≥2 crises)
                       └─▶ REPLICATED  (independent re-run)
                            └─▶ VALIDATED  (peer-reviewed)
```

Current status: **HYPOTHESIS / SCORE-LEVEL INSTRUMENTATION COMPLETE; END-TO-END VALIDATION PENDING**.

The pre-registered falsification battery operates on a *score
series*. The full pipeline — temporal exposure panel → topology →
coupling → Kuramoto dynamics → r(t) → early-warning score → verdict
— is not yet end-to-end executable. The composed null-audit
orchestrator (`null_models.run_null_audit`) is documented as
deferred until empirical temporal-exposure ingest lands; promotion
gates beyond `INSTRUMENTED + TESTED_ON_SYNTHETIC` therefore cannot
fire from the current main.
