---
owner: data@tradepulse
review_cadence: quarterly
last_reviewed: 2025-12-28
links:
  - docs/dataset_catalog.md
  - docs/architecture/feature_store.md
  - docs/model_cards/market_regime_classifier.md
---

# Dataset Card: Feature Store Market Snapshot

## Overview

- **Owner:** Data Platform
- **Source System:** feature store offline snapshots (Delta Lake/Iceberg)
- **Data Version:** `fs_market_snapshot_v2025_02`
- **Generating Pipeline Version:** `core.data.materialization` + `core.data.feature_store`
- **Refresh Cadence:** hourly
- **Access Controls:** internal-only, role-based data lake policies

## Dataset Description

- **Time Range:** 2021-01-01 → 2025-02-28
- **Entities/Coverage:** top 250 traded instruments across venues
- **Granularity:** 1m, 5m, 1h aggregates
- **Primary Use Cases:** regime classification, risk overlays, backtest baselines

## Schema Summary

| Field | Type | Description | Example |
| ----- | ---- | ----------- | ------- |
| `timestamp` | datetime | feature window close time | `2025-02-28T14:00:00Z` |
| `instrument_id` | string | canonical instrument key | `BTC-USD` |
| `volatility_1h` | float | annualized 1h volatility | `0.42` |
| `liquidity_score` | float | normalized liquidity index | `0.78` |
| `spread_bps` | float | avg bid-ask spread in bps | `4.2` |

## Data Collection & Processing

- **Collection Method:** streaming market feeds ingested via `StreamMaterializer`
- **Cleaning/Filtering Steps:** dedupe, late-arrival correction, null imputation
- **Labeling/Annotation:** regime labels derived from volatility + flow heuristics
- **Known Gaps or Biases:** thinly traded instruments may under-report liquidity

## Splits & Partitions

- **Train/Validation/Test:** time-based splits by quarter
- **Sampling Strategy:** proportional sampling by instrument liquidity tier
- **Recommended Slice Checks:** high-volatility regime, low-liquidity assets

## Quality & Validation

- **Checks Performed:** schema validation, missing data checks, drift checks
- **Known Quality Issues:** occasional backfill delays during exchange outages
- **Monitoring Signals:** null-rate thresholds, schema drift alerts

## Drift Risks & Monitoring

- **Drift Risks:** structural shifts in spread/volatility during macro events
- **Monitoring Hooks:**
  - feature drift dashboards in `docs/risk_ml_observability.md`
  - online/offline parity checks via `OfflineStoreValidator`

## Usage Notes

- **Required Context/Assumptions:** assumes synchronized timestamps across venues
- **Limitations:** not suitable for tick-level microstructure analysis
- **Related Models:** [Market Regime Classifier](../model_cards/market_regime_classifier.md)

## Compliance & Privacy

- **PII/PCI Handling:** none
- **Retention Policy:** aligns with feature store TTL and audit retention windows
- **Licensing/Restrictions:** market data subject to vendor agreements

## Change History

| Date | Author | Change |
| ---- | ------ | ------ |
| 2025-03-15 | tradepulse-data | Initial draft |
