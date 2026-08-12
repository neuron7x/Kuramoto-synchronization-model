# Production Deployment Protocol v1.0

This repository-native runbook operationalizes the production sequence for GeoSync substrate validation and deployment.

## Deterministic Constraints
- Global seed: `42`.
- UTC timestamps only.
- Hard abort on invariant violations (NaN, stale feed, schema drift, orthogonality gate fail).
- No fallback that can fabricate a positive signal.

## Required Artifacts
- `audit/prod/provider_manifest.json`
- `data/cache/panel_raw.parquet`
- `data/cache/panel_canonical.parquet`
- `data/cache/panel_enriched.parquet`
- `data/cache/unity_signal.parquet`
- `results/prod/validation_verdict.json`
- `results/prod/action_intent.json`
- `audit/prod/run_hash.sha256`

## Sentiment Node / Ricci Experiment
Use the experiment script with explicit source selection:

```bash
PYTHONPATH=. python research/askar/sentiment_node_ricci_graph.py \
  --panel data/askar_full/panel_hourly_extended.parquet \
  --output results/sentiment_node_verdict.json \
  --source vix
```

To use Reddit sentiment instead of VIX proxy, set:
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT` (optional)

Then run with `--source reddit`.

## Gate Policy
Signal is deployable only if all pass:
- `IC >= 0.08`
- `p_value < 0.10`
- `abs(corr_momentum) < 0.15`
- `abs(corr_vol) < 0.15`
- `lead_capture >= 0.60`

Otherwise: `FINAL = REJECT` and action must remain `DORMANT`.

## Abort Procedure
On any abort criterion:
1. write `abort_log.json` in audit dir
2. set agent state `DORMANT`
3. stop signal publication
4. notify ops

## Sign-off
- Deployment executed by: __________
- Validation by: __________
- Approved by: __________
- Date (UTC): __________
