---
owner: mlops@geosync
review_cadence: quarterly
last_reviewed: 2025-12-28
links:
  - docs/devops/mlops-orchestration.md
  - docs/feature_store_sync_and_registry.md
  - docs/documentation_standardisation_playbook.md
---

# Model Card: <Model Name>

<details>
<summary>How to use this template</summary>

- Store model cards under `docs/models/` or `docs/model_cards/` and cross-link
  from relevant runbooks or the release ticket.
- Capture **data_version** and **code_version** for every released model
  artifact; these should match the experiment registry metadata.
- Link to the dataset card(s) that describe training and evaluation datasets.
- Remove this guidance before publishing.

</details>

## Overview

- **Owner:**
- **Primary Contact:**
- **Lifecycle Stage:** research / staging / production / retired
- **Model Type:** (e.g., gradient boosting, transformer)
- **Inference Interface:** (batch / streaming / API)

## Intended Use

- **Target Users/Systems:**
- **Supported Markets/Assets:**
- **Business Objectives:**
- **Out-of-Scope Uses:**

## Data Lineage

- **Training Dataset(s):** (link to dataset card)
- **Training Data Version:** `<data_version>`
- **Evaluation Dataset(s):** (link to dataset card)
- **Evaluation Data Version(s):**
- **Data Refresh Cadence:**

## Model Lineage

- **Code Version:** `<code_version>` (git SHA or release tag)
- **Training Pipeline Version:**
- **Hyperparameter Set/Hash:**
- **Artifact URI:** (registry path or storage URI)

## Training & Evaluation

- **Training Window:**
- **Feature Set:** (link to feature catalog entry if applicable)
- **Metrics:** (e.g., Sharpe, precision/recall, latency)
- **Baseline Comparison:**

## Performance Notes

- **Key Strengths:**
- **Observed Failure Modes:**
- **Stress/Robustness Tests:**

## Risk & Compliance

- **Bias/Drift Considerations:**
- **Security/PII Handling:**
- **Regulatory Notes:**

## Reproducibility

- **Random Seeds:** (where applied)
- **Dependency Lockfile:** (path or version)
- **Runtime Environment:** (container image, OS, hardware)

## Change History

| Date | Author | Change |
| ---- | ------ | ------ |
| YYYY-MM-DD | name | Initial draft |
