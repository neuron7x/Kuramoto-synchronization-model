# BASELINES — research/systemic_risk

> What simple explanation could defeat our candidate signal?

The candidate Kuramoto-on-interbank score must outperform every
baseline below on every pre-registered metric. A baseline that
matches or beats the candidate is the disconfirming explanation
for the apparent signal — under the v2 falsification contract,
the candidate cannot advance beyond `HYPOTHESIS / SCORE-LEVEL
INSTRUMENTATION EXTENSION` until *every* baseline is dominated.

## Naive baselines (this PR)

* **`baselines.rolling_volatility_score`** — trailing-window sample
  standard deviation of the spread series. Pure volatility
  detector with zero phase / coupling structure.
  *Defeats the candidate when:* the apparent pre-event elevation
  is just the market being loud.
* **`baselines.edge_density_score`** — per-snapshot edge density of
  the directed adjacency. One scalar per timestamp; no dynamics.
  *Defeats the candidate when:* the apparent pre-event signal is
  just the graph densifying or sparsifying around crises.

## Six null surrogates (delivered in PR #562)

See `NULL_MODELS.md` and the `null_models.py` docstring for the
full list. The composed `run_null_audit` orchestrator is deferred
until empirical-data ingest lands.

## What it means if any baseline wins

* Baseline AUC ≥ candidate AUC on the same crisis set ⇒ the
  Kuramoto-specific structure adds nothing in that regime; promote
  the baseline narrative, not the candidate.
* Baseline CI overlaps the candidate CI under a stratified
  bootstrap ⇒ the comparison is statistically inconclusive; the
  promotion gate stays closed regardless of the point estimate.
* Baseline beats the candidate on lead-time but loses on AUC ⇒
  **document the trade-off explicitly**; do not pick the metric
  that flatters the candidate.

## What this PR does NOT claim

* No baseline run has been executed against real interbank data.
* No baseline outcome is on file.
* Synthetic rails (PR #562's `test_random_scores_do_not_pass` /
  `test_injected_signal_passes`) demonstrate that the
  *machinery* is calibrated — they do not constitute baseline-vs-
  candidate evidence on real data.

The `MEASURED` tier requires the full baseline matrix run on a
pre-registered, manifest-bound real-data execution.
