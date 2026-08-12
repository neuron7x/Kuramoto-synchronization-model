# NULL_MODELS — research/systemic_risk

> The six pre-registered null surrogates. A claimed positive must
> survive *all six* before any promotion beyond `HYPOTHESIS`.

## The six surrogates

| # | Generator | What it preserves | What it destroys |
|---|-----------|-------------------|------------------|
| 1 | `degree_preserving_randomization` | per-node in-degree + out-degree | edge incidences, motifs |
| 2 | `shuffled_time_labels` | marginal score distribution | temporal ordering |
| 3 | `random_exposure_weights` | binary support graph | exposure magnitudes |
| 4 | `static_topology_baseline` | union of edges across snapshots | temporal evolution of the graph |
| 5 | `linear_correlation_surrogate` | mean cross-correlation level | non-linearity of phase coupling |
| 6 | `permuted_crisis_dates` | per-event duration distribution | crisis-date timing |

Source: `null_models.py`. Each generator returns a
`NullSurrogate` with explicit seed.

## Executable status

The composed orchestrator `run_null_audit(...)` that runs all six
generators and emits a `pass_all` verdict is **deferred** until
empirical temporal-exposure ingest lands. Today, callers compose
the surrogates manually:

* score-replacing surrogates (`shuffled_time_labels`,
  `linear_correlation_surrogate`) feed `run_falsification` /
  `run_score_level_falsification` directly;
* topology-replacing surrogates (`degree_preserving_randomization`,
  `random_exposure_weights`, `static_topology_baseline`) feed the
  upstream score-construction stack the caller maintains.

## Promotion gate

No promotion path depends on a non-existent executable gate.
`PROTOCOL.md § 4` enumerates the six surrogates as a
*requirement*; the requirement is satisfied at the
`MEASURED`-promotion review by the manifest-bound run report
documenting per-baseline AUC + CI + p, not by a wishful CI
assertion in the current main.

## What this PR does NOT add

* No `run_null_audit` orchestrator. Adding one in the absence of a
  temporal-exposure ingest would be a partial pipeline that could
  be misread as end-to-end evidence — that risk is the explicit
  reason for the deferral (see `governance.run_premerge_science_gate`
  + `falsification.run_end_to_end_falsification` stub).
