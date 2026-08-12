# Offline↔Online Feature Store Parity and Model Registry Blueprint

This blueprint defines the guardrails required to keep GeoSync's offline
research environment aligned with the online scoring path and to formalise how
models are registered, promoted, and rolled back. The controls apply to both
feature pipelines and the lifecycle of ML models deployed into production.

---

## 1. Offline↔Online Parity Controls

| Area | Control | Implementation Notes | Validation Signals |
| --- | --- | --- | --- |
| **Feature Definitions** | Version feature transformations with immutable hashes derived from source code, dependency versions, and configuration payloads. | Embed the hash in `FeatureManifest` records and inject into scoring payload headers. Reject online payloads whose hash is not present in the active manifest catalogue. | Metrics: `geosync_feature_manifest_mismatch_total` (counter) and `geosync_feature_manifest_active` (gauge with hash label). |
| **Data Windows** | Align windowing semantics (look-back horizons, sampling cadence, timezone boundaries) between offline generation jobs and online streaming consumers. | Source canonical window specs from `configs/features/windows.yaml`. Compile specs into protobuf payloads consumed by both batch and streaming runners. | Automated diff job comparing offline parquet partitions vs. online cache snapshots with Wasserstein distance threshold ≤ 0.02. |
| **Feature Value Drift** | Continuously compare live feature distributions to most recent backtest snapshots. | Persist offline feature histograms in MLflow artifacts; stream online histograms via Prometheus histograms. Run scheduled Kolmogorov–Smirnov test; alert when p-value < 0.01 for two consecutive windows. | Alert: `FeatureDriftAlert` routed to `#quant-ops`. |
| **Dependency Pinning** | Ensure identical dependency sets (Python packages, model binaries) between offline training containers and live inference pods. | Publish lockfiles to OCI registry; deploy online services from the same digest used to run the offline pipeline. | CI job `make parity-verify` reconstructs containers and validates SHA256 digests. |
| **Schema Evolution** | Guard against breaking schema changes by enforcing backwards-compatible evolution and timestamped migrations. | Use `core.messaging.EventSchemaRegistry` for feature payload schemas; require schema update proposals with automated backward-compatibility checks. | CI asserts new schemas append-only and include migration notes in `docs/changelog/features.md`. |

### 1.1 Synchronisation Workflows

1. **Manifest Promotion** – Offline pipeline publishes manifests to `s3://geosync-feature-manifests/<hash>.json`. Deployment workflow promotes manifest by updating `configs/features/active_manifest.yaml` with hash + timestamp.
2. **Online Warm-Up** – Before switching manifests, run warm-up job that replays last N minutes of market data through the new manifest to confirm parity metrics remain within tolerance.
3. **Gatekeeper Check** – Canary scoring pods subscribe to manifest change events. If feature parity checks fail, canary stays isolated and production keeps the previous manifest.

### 1.2 Offline↔Online Regression Tests

- **Snapshot Comparison Test** – Nightly job loads offline parquet snapshot and the online Redis cache for the same horizon; asserts max absolute difference < policy threshold per feature.
- **Latency Budget Test** – Validate online feature computation latency remains below 150 ms p95. Uses synthetic load harness with recorded market data bursts.
- **Reproducibility Test** – Re-run latest offline training job using archived manifest; assert resulting features match hashed artifacts and aggregated metrics stored in MLflow within tolerance.

---

## 2. Online Following (Real-Time Signal Tracking) Tests

| Test | Purpose | Tooling | Pass Criteria |
| --- | --- | --- | --- |
| **Signal Shadowing** | Compare live trading signals vs. offline replay predictions for current market window. | Deploy shadow service subscribing to production inputs and writing signals to `signals.shadow` topic. Offline job replays same inputs with current model artifacts. | Mean absolute percentage difference (MAPD) ≤ 1% over rolling 1-hour windows. |
| **Decision Drift Audit** | Detect divergence in downstream trading decisions (orders) caused by signal gaps. | Instrument execution service to tag orders with model + manifest hashes; nightly audit compares offline recommended orders vs. executed ones. | ≥ 99% of orders share identical hashes; discrepancies require manual review ticket. |
| **Latency Regression** | Ensure online following pipeline adheres to SLA during volatile bursts. | Integration test harness generates synthetic burst load (5× baseline). Measure end-to-end time from data ingestion to signal emission. | p99 latency ≤ 250 ms; drop rate = 0. |
| **Failover Simulation** | Validate online pipeline recovery after cache flush or Kafka partition reassignment. | Chaos cron triggers failover twice per week; monitor replay catch-up metrics. | Catch-up duration < 2 minutes; no data gaps in `signals.audit` topic. |

Operational checklist:

- Track metrics `geosync_signal_shadow_mape`, `geosync_signal_follow_latency_seconds`, and `geosync_signal_follow_replay_lag_seconds` in Grafana dashboard `Signal Following`.
- Store test results under `reports/online_following/<date>.md` with summary tables and remediation actions.

---

## 3. Model Registry and Deployment Controls

| Capability | Description | Implementation Notes |
| --- | --- | --- |
| **Registry Backend** | Centralise model metadata using MLflow or a compatible custom backend. | MLflow tracking URI `mlflow://registry` with PostgreSQL backend store. For bespoke backend, reuse `core.reporting` persistence interfaces. |
| **Artefact Management** | Store model binaries, feature manifests, and supporting metadata per run. | Package artefacts as OCI images or tarballs. Upload to registry with structured directories (`artifacts/{model_name}/{version}/`). Include checksum manifest. |
| **Metrics & Evaluation Records** | Capture offline evaluation metrics and online health KPIs. | MLflow metrics: `roc_auc`, `precision@k`, `annualized_return`, `drawdown`. Append online metrics (latency, drift) via registry callbacks. |
| **Configuration Signatures** | Generate signed digests of training + serving configuration. | Use SHA256 of canonicalised YAML configs; store signature + signing certificate in registry metadata. Verify during deployment gating. |
| **Lineage Tracking** | Link models to data sources, feature manifests, and code revisions. | Add MLflow tags: `git_commit`, `feature_manifest_hash`, `data_snapshot_id`. Persist JSON lineage graph to `reports/models/<model>/lineage.json`. |
| **Access Controls** | Enforce RBAC for model registration, promotion, and rollback. | Integrate registry with IAM roles (`role:quant`, `role:mlops`, `role:sre`). Promotion requires two-person review logged in `observability/audit/model_events.jsonl`. |

### 3.1 Promotion Workflow

1. **Staging Validation** – Deploy candidate model to staging with latest manifest; run regression + drift simulation suites.
2. **Canary Release** – Spin up canary deployment serving a fraction (5–10%) of live traffic. Publish metrics to separate Prometheus job (`geosync_canary_*`).
3. **Automated Guardrails** – If canary metrics breach thresholds (latency, drift, PnL deltas), trigger automatic rollback via registry event `rollback.requested`.
4. **Promotion Decision** – Upon success, update registry stage to `Production` and tag deployment record with `approved_by` users.

### 3.2 Canary & Rollback Procedures

- **Rollback Playbook** – Use `deploy/model_ctl.py rollback --model <name> --target <version>` which fetches artefacts and config signatures, updates inference service, and notifies incident channel.
- **Canary Scorecard** – Maintain `reports/models/<model>/canary_scorecard.md` documenting metrics before/after canary. Scorecard must include `latency_p95`, `psi`, `sharpe_delta`, and `order_fill_rate` comparisons.
- **Audit Trail** – Append JSON entry to `observability/audit/model_events.jsonl` with fields `{timestamp, model, from_version, to_version, initiated_by, outcome}`.

### 3.3 Registry Testing

| Test | Focus | Frequency |
| --- | --- | --- |
| **Metadata Integrity Check** | Validate each model version includes artefact checksum, config signature, and evaluation metrics. | Nightly CI job `make registry-validate`. |
| **Rollback Dry Run** | Simulate rollback to previous stable version using staging infrastructure. | Weekly. |
| **Access Control Audit** | Review registry access logs for policy violations and confirm multi-approver workflow functioning. | Monthly with SRE + Security. |
| **Lineage Consistency Test** | Cross-check registry lineage metadata vs. stored manifests and Git history. | Post-release. |

---

## 4. Reporting and Communication

- Publish parity and registry status in weekly `Model Governance` meeting notes.
- Update `reports/models/registry_summary.md` with latest approved versions, outstanding actions, and audit findings.
- Maintain confluence-style quick links in `docs/index.md` once available to surface manifest hashes, latest canary scorecards, and rollback logs.

Following these practices ensures GeoSync maintains strong control over
offline/online parity while delivering predictable and auditable model
deployments.
