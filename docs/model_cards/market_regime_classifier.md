---
owner: mlops@tradepulse
review_cadence: quarterly
last_reviewed: 2025-12-28
links:
  - docs/devops/mlops-orchestration.md
  - docs/architecture/feature_store.md
  - docs/datasets/market_feature_snapshot.md
---

# Model Card: Market Regime Classifier

## Overview

- **Owner:** MLOps Enablement
- **Primary Contact:** mlops@tradepulse
- **Lifecycle Stage:** staging
- **Model Type:** gradient boosting classifier
- **Inference Interface:** batch + streaming

## Intended Use

- **Target Users/Systems:** strategy selection, risk overlays, and real-time guards
- **Supported Markets/Assets:** multi-asset futures + spot baskets
- **Business Objectives:** classify market regimes to adjust risk budgets
- **Out-of-Scope Uses:** single-asset forecasting, client-facing advisory

## Data Lineage

- **Training Dataset(s):** [Feature Store Market Snapshot](../datasets/market_feature_snapshot.md)
- **Training Data Version:** `fs_market_snapshot_v2025_02`
- **Evaluation Dataset(s):** [Feature Store Market Snapshot](../datasets/market_feature_snapshot.md)
- **Evaluation Data Version(s):** `fs_market_snapshot_v2025_02_eval`
- **Data Refresh Cadence:** hourly snapshot rollups

## Model Lineage

- **Code Version:** `git: TBD`
- **Training Pipeline Version:** `scripts/mlops/github_actions_pipeline`
- **Hyperparameter Set/Hash:** `regime_cls_gbm_v3`
- **Artifact URI:** `artifacts/model-registry/experiments/regime-classifier/latest`

## Training & Evaluation

- **Training Window:** 2022-01-01 → 2024-12-31
- **Feature Set:** [Feature store catalog](../feature_store_sync_and_registry.md)
- **Metrics:** regime accuracy, macro-F1, drawdown delta, latency p95
- **Baseline Comparison:** rule-based volatility buckets (2024-11 benchmark)

## Performance Notes

- **Key Strengths:** stable regime labeling during volatility spikes; strong macro-F1
- **Observed Failure Modes:** regime lag during sudden liquidity withdrawal
- **Stress/Robustness Tests:** volatility shocks, missing-feed ablations

## Risk & Compliance

- **Bias/Drift Considerations:** regime distribution shifts when market microstructure changes
- **Drift Risks:** increased false positives during macro announcements or exchange outages
- **Monitoring Hooks:**
  - feature drift checks in `docs/risk_ml_observability.md`
  - online/offline parity via `OfflineStoreValidator`
- **Security/PII Handling:** no PII; market data only
- **Regulatory Notes:** internal decision support; no client disclosure

## Reproducibility

- **Random Seeds:** fixed per training run in registry metadata
- **Dependency Lockfile:** `requirements.lock`
- **Runtime Environment:** `ghcr.io/<repo>/mlops:<sha>`

## Change History

| Date | Author | Change |
| ---- | ------ | ------ |
| 2025-03-15 | tradepulse-mlops | Initial draft |
